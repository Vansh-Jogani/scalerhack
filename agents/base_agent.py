import asyncio
import structlog
from anthropic import AsyncAnthropic

logger = structlog.get_logger()


class BaseAgent:
    """Base agent with observe/reason/act loop. Agents inherit and configure."""

    def __init__(self, agent_id: str, system_prompt: str, model: str, world_state, drone_ids: list[str], tools: list[dict], interval: float = 2.0):
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.model = model
        self.world_state = world_state
        self.drone_ids = drone_ids
        self.tools = tools
        self.interval = interval
        self.client = AsyncAnthropic()
        self._running = False
        self._tool_handlers: dict[str, callable] = {}

    def register_tool(self, name: str, handler: callable):
        self._tool_handlers[name] = handler

    async def observe(self) -> dict:
        markers = self.world_state.get_markers()
        telemetry = [self.world_state.get_drone_telemetry(d) for d in self.drone_ids]
        return {
            "markers": [m.model_dump() for m in markers],
            "drone_telemetry": [t.__dict__ if t else None for t in telemetry],
        }

    async def reason(self, observations: dict) -> dict:
        messages = [
            {"role": "user", "content": f"Current observations:\n{observations}"}
        ]
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self.system_prompt,
            messages=messages,
            tools=self.tools,
        )
        return response

    async def act(self, response) -> list[dict]:
        results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                handler = self._tool_handlers.get(tool_name)
                if handler:
                    result = await handler(**tool_input)
                    results.append({"tool": tool_name, "input": tool_input, "result": result})
                    logger.info("tool_executed", agent=self.agent_id, tool=tool_name, input=tool_input)
                else:
                    logger.warning("unknown_tool", agent=self.agent_id, tool=tool_name)
        return results

    async def run(self):
        self._running = True
        logger.info("agent_started", agent=self.agent_id)
        while self._running:
            try:
                observations = await self.observe()
                response = await self.reason(observations)
                await self.act(response)
            except Exception as e:
                logger.error("agent_error", agent=self.agent_id, error=str(e))
            await asyncio.sleep(self.interval)

    def stop(self):
        self._running = False
