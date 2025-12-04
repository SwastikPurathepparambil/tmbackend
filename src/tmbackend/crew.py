# from crewai import Agent, Crew, Process, Task
# from crewai.project import CrewBase, agent, crew, task
# from crewai.agents.agent_builder.base_agent import BaseAgent
# from typing import List
# # If you want to run a snippet of code before or after the crew starts,
# # you can use the @before_kickoff and @after_kickoff decorators
# # https://docs.crewai.com/concepts/crews#example-crew-class-with-decorators

# @CrewBase
# class Tmbackend():
#     """Tmbackend crew"""

#     agents: List[BaseAgent]
#     tasks: List[Task]

#     # Learn more about YAML configuration files here:
#     # Agents: https://docs.crewai.com/concepts/agents#yaml-configuration-recommended
#     # Tasks: https://docs.crewai.com/concepts/tasks#yaml-configuration-recommended
    
#     # If you would like to add tools to your agents, you can learn more about it here:
#     # https://docs.crewai.com/concepts/agents#agent-tools
#     @agent
#     def researcher(self) -> Agent:
#         return Agent(
#             config=self.agents_config['researcher'], # type: ignore[index]
#             verbose=True
#         )

#     @agent
#     def reporting_analyst(self) -> Agent:
#         return Agent(
#             config=self.agents_config['reporting_analyst'], # type: ignore[index]
#             verbose=True
#         )

#     # To learn more about structured task outputs,
#     # task dependencies, and task callbacks, check out the documentation:
#     # https://docs.crewai.com/concepts/tasks#overview-of-a-task
#     @task
#     def research_task(self) -> Task:
#         return Task(
#             config=self.tasks_config['research_task'], # type: ignore[index]
#         )

#     @task
#     def reporting_task(self) -> Task:
#         return Task(
#             config=self.tasks_config['reporting_task'], # type: ignore[index]
#             output_file='report.md'
#         )

#     @crew
#     def crew(self) -> Crew:
#         """Creates the Tmbackend crew"""
#         # To learn how to add knowledge sources to your crew, check out the documentation:
#         # https://docs.crewai.com/concepts/knowledge#what-is-knowledge

#         return Crew(
#             agents=self.agents, # Automatically created by the @agent decorator
#             tasks=self.tasks, # Automatically created by the @task decorator
#             process=Process.sequential,
#             verbose=True,
#             # process=Process.hierarchical, # In case you wanna use that instead https://docs.crewai.com/how-to/Hierarchical/
#         )

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from crewai import Agent, Task, Crew


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_crew(
    tool_instances: Optional[Dict[str, Any]] = None,
    task_names: Optional[List[str]] = None,
) -> Crew:
    """
    Build a Crew from YAML configs, optionally injecting runtime-built tools and
    selecting a subset/order of tasks to run.

    - tool_instances: dict of {tool_name: tool_instance} to attach to agents
    - task_names: ordered list of task keys from tasks.yaml to run
                  (defaults to the resume-only pipeline)
    """
    src_dir = Path(__file__).resolve().parent
    config_dir = src_dir / "config"

    agents_cfg = _load_yaml(config_dir / "agents.yaml")["agents"]
    tasks_cfg = _load_yaml(config_dir / "tasks.yaml")["tasks"]

    tools = tool_instances or {}

    # ---- Agents ----
    agents: Dict[str, Agent] = {}
    for name, cfg in agents_cfg.items():
        # Only attach tools that were actually injected/built.
        agent_tools = [tools[t] for t in cfg.get("tools", []) if t in tools]
        agents[name] = Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg.get("backstory", ""),
            verbose=bool(cfg.get("verbose", False)),
            tools=agent_tools,
        )

    # ---- Tasks (create all first) ----
    all_tasks: Dict[str, Task] = {}
    for name, cfg in tasks_cfg.items():
        all_tasks[name] = Task(
            description=cfg["description"],
            expected_output=cfg["expected_output"],
            agent=agents[cfg["agent"]],
            async_execution=bool(cfg.get("async_execution", False)),
            output_file=cfg.get("output_file"),  # remove/comment in YAML if you want zero writes
        )

    # Wire contexts by task name
    for name, cfg in tasks_cfg.items():
        ctx_names = cfg.get("context", [])
        if ctx_names:
            all_tasks[name].context = [all_tasks[c] for c in ctx_names if c in all_tasks]

    # ---- Choose which tasks to run (order matters) ----
    order = task_names or ["research_task", "profile_task", "resume_strategy_task"]
    selected_tasks = [all_tasks[n] for n in order if n in all_tasks]

    return Crew(
        agents=list(agents.values()),
        tasks=selected_tasks,
        verbose=True,
    )