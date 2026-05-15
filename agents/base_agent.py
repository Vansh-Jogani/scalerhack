"""Base agent with OODA-R loop (Observe → Orient/Reason → Act → Reflect).

All agents inherit from BaseAgent. BaseAgent never calls an LLM directly —
subclasses define the model and system prompt via __init__.

Per SPEC.md:
- observe() reads from SHARED_TO_AGENTS only
- reason() calls LLM with system prompt + tools (multi-turn)
- act() executes tool calls, writes to SHARED_TO_SIMULATION
- reflect() logs to Omium tracer, updates state sub-key
- Loop runs until agent receives COMPLETE or ABORT
"""

import asyncio
import json
from abc import ABC, abstractmethod

import structlog
from anthropic import AsyncAnthropic

from sim_layer.tracer import tracer

logger = structlog.get_logger()


class BaseAgent(ABC):
    """Abstract base agent implementing the OODA-R loop.

    Subclasses MUST provide:
      - system_prompt (str)
      - model (str)
      - tools (list[dict]) — Anthropic tool schemas
      - _tool_handlers (dict[str, callable]) — name → async handler
    """

    def __init__(
        self,
        agent_id: str,
        system_prompt: str,
        model: str,
        world_state,
        sensor_overlay,
        drone_ids: list[str],
        tools: list[dict],
        tool_handlers: dict[str, callable],
        interval: float = 2.0,
        stream_callback=None,
    ):
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.model = model
        self.world_state = world_state
        self.sensor_overlay = sensor_overlay
        self.drone_ids = drone_ids
        self.tools = tools
        self._tool_handlers = tool_handlers
        self.interval = interval
        self.stream_callback = stream_callback

        self.client = AsyncAnthropic()
        self._running = False
        self._conversation: list[dict] = []
        self._span = None

    # ------------------------------------------------------------------
    # OODA-R methods
    # ------------------------------------------------------------------

    async def observe(self) -> dict:
        """Read from SHARED_TO_AGENTS only — markers + drone telemetry.

        Subclasses can extend (call super().observe() then add mission context)
        but MUST NOT read from HIDDEN_FROM_AGENTS.
        """
        markers = self.world_state.get_markers()
        telemetry = []
        for did in self.drone_ids:
            t = self.world_state.get_drone_telemetry(did)
            if t is not None:
                telemetry.append(t.__dict__)
        return {
            "markers": [m.model_dump() for m in markers],
            "drone_telemetry": telemetry,
        }

    async def reason(self, observations: dict) -> object:
        """Call Claude API with system prompt + tools.

        Uses conversation history for multi-turn tool use.
        Subclasses configure model and system_prompt — never override this.
        """
        # Build user message with current observations
        user_msg = {
            "role": "user",
            "content": f"Current observations:\n{json.dumps(observations, default=str)}",
        }
        self._conversation.append(user_msg)

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self.system_prompt,
                messages=self._conversation,
                tools=self.tools,
            )
        except Exception as api_err:
            logger.error("anthropic_api_reason_error", error=str(api_err), type=str(type(api_err)), exc_info=True)
            raise

        # Store assistant response in conversation history
        self._conversation.append({"role": "assistant", "content": response.content})

        return response

    async def act(self, response) -> list[dict]:
        """Execute tool_use blocks from LLM response.

        Calls registered tool handlers. Returns list of {tool, input, result}.
        """
        results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                handler = self._tool_handlers.get(tool_name)
                if handler:
                    try:
                        result = await handler(**tool_input)
                    except Exception as e:
                        result = {"status": "error", "message": str(e)}
                        logger.error("tool_error", agent=self.agent_id, tool=tool_name, error=str(e))
                    results.append({
                        "tool": tool_name,
                        "tool_use_id": block.id,
                        "input": tool_input,
                        "result": result,
                    })
                    logger.info("tool_executed", agent=self.agent_id, tool=tool_name)
                else:
                    logger.warning("unknown_tool", agent=self.agent_id, tool=tool_name)
                    results.append({
                        "tool": tool_name,
                        "tool_use_id": block.id,
                        "input": tool_input,
                        "result": {"status": "error", "message": f"Unknown tool: {tool_name}"},
                    })

        return results

    async def reflect(self, results: list[dict]) -> None:
        """Log to Omium tracer. Updates agent's state sub-key."""
        for r in results:
            tracer.record_event(
                f"{self.agent_id}.tool_result",
                tool=r["tool"],
                status=r["result"].get("status", "unknown"),
            )

        if self.stream_callback and results:
            await self._emit("tool_results", {
                "tools": [r["tool"] for r in results],
                "count": len(results),
            })

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self, initial_message: str | None = None) -> None:
        """Run the OODA-R loop until COMPLETE or ABORT.

        If initial_message is provided, it's used as the first user message
        instead of observations (for GO signal scenarios).

        Handles multi-turn tool use: if LLM returns tool_use blocks,
        we execute them, feed tool_results back, and re-reason.
        """
        self._running = True
        self._span = tracer.start_span(f"{self.agent_id}.run")
        logger.info("agent_started", agent=self.agent_id, model=self.model)

        if self.stream_callback:
            await self._emit("started", {"model": self.model, "drones": self.drone_ids})

        try:
            # If initial message provided, use it as first user message
            if initial_message:
                self._conversation.append({"role": "user", "content": initial_message})
                try:
                    response = await self.client.messages.create(
                        model=self.model,
                        max_tokens=2048,
                        system=self.system_prompt,
                        messages=self._conversation,
                        tools=self.tools,
                    )
                    self._conversation.append({"role": "assistant", "content": response.content})

                    # Multi-turn tool use loop for initial message
                    await self._process_tool_loop(response)
                except Exception as api_err:
                    logger.error("anthropic_api_error", error=str(api_err), type=str(type(api_err)), exc_info=True)
                    raise

            # Main OODA-R loop
            while self._running:
                try:
                    observations = await self.observe()
                    response = await self.reason(observations)
                    await self._process_tool_loop(response)
                except Exception as e:
                    logger.error("agent_loop_error", agent=self.agent_id, error=str(e))

                await asyncio.sleep(self.interval)

        finally:
            if self._span:
                self._span.__exit__(None, None, None)
            logger.info("agent_stopped", agent=self.agent_id)

    async def _process_tool_loop(self, response) -> None:
        """Handle multi-turn tool use.

        If the LLM response contains tool_use blocks:
        1. Execute all tools via act()
        2. Log via reflect()
        3. Feed tool_results back to the LLM
        4. Repeat until LLM returns text-only (end_turn)

        This allows Claude to chain multiple tool calls in sequence.
        """
        max_turns = 15  # safety cap to prevent infinite loops

        for _ in range(max_turns):
            # Check if response has tool_use blocks
            has_tools = any(b.type == "tool_use" for b in response.content)
            if not has_tools:
                # LLM returned text only — check for completion signals
                text = self._extract_text(response)
                if text:
                    logger.info("agent_text", agent=self.agent_id, text=text[:200])
                    if self.stream_callback:
                        await self._emit("reasoning", {"text": text})

                    # Check for completion
                    if any(signal in text.lower() for signal in ["mission complete", "classification reported", "survey complete"]):
                        self.stop()
                break

            # Execute tools
            results = await self.act(response)
            await self.reflect(results)

            # Feed tool results back to Claude for next turn
            tool_results = []
            for r in results:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": r["tool_use_id"],
                    "content": json.dumps(r["result"], default=str),
                })

            self._conversation.append({"role": "user", "content": tool_results})

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self.system_prompt,
                messages=self._conversation,
                tools=self.tools,
            )
            self._conversation.append({"role": "assistant", "content": response.content})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_text(self, response) -> str:
        """Extract text content from an Anthropic response."""
        parts = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts)

    async def _emit(self, event: str, content) -> None:
        """Emit event to stream callback if registered."""
        if self.stream_callback:
            try:
                await self.stream_callback("agent_stream", {
                    "agent_id": self.agent_id,
                    "event": event,
                    "content": content,
                })
            except Exception as e:
                logger.warning("emit_error", agent=self.agent_id, error=str(e))

    def stop(self) -> None:
        """Signal the agent to stop its OODA-R loop."""
        self._running = False

    def reset_conversation(self) -> None:
        """Clear conversation history for a fresh start."""
        self._conversation = []
