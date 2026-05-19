import { AgentSupervisor, AgentSupervisorSnapshot } from "./agent-supervisor";
import { MetricsRecorder } from "../06-observability/metrics";

export interface AgentFleetPolicy {
  desiredActiveAgents: number;
  minActiveAgents?: number;
  minWorkingAgents?: number;
  maxActiveAgents?: number;
}

export interface AgentFleetSnapshot {
  desiredActiveAgents: number;
  totalAgents: number;
  activeAgents: number;
  readyAgents: number;
  workingAgents: number;
  notWorkingAgents: number;
  allAgentsWorking: boolean;
  warmingAgents: number;
  degradedAgents: number;
  stoppedAgents: number;
}

export interface AgentFleetSupervisorOptions {
  policy?: AgentFleetPolicy;
  metrics?: MetricsRecorder;
  supervisorFactory: (index: number) => AgentSupervisor;
}

const DEFAULT_DESIRED_ACTIVE_AGENTS = 100;

export class AgentFleetSupervisor {
  private readonly desiredActiveAgents: number;
  private readonly minActiveAgents: number;
  private readonly maxActiveAgents: number;
  private readonly minWorkingAgents: number;
  private readonly metrics: MetricsRecorder;
  private readonly supervisors: AgentSupervisor[] = [];

  constructor(private readonly options: AgentFleetSupervisorOptions) {
    const policy = options.policy ?? { desiredActiveAgents: DEFAULT_DESIRED_ACTIVE_AGENTS };
    this.desiredActiveAgents = policy.desiredActiveAgents;
    this.minActiveAgents = policy.minActiveAgents ?? policy.desiredActiveAgents;
    this.maxActiveAgents = policy.maxActiveAgents ?? policy.desiredActiveAgents;
    this.minWorkingAgents = policy.minWorkingAgents ?? policy.desiredActiveAgents;
    this.metrics = options.metrics ?? new MetricsRecorder();
    this.validatePolicy();
  }

  async reconcile(): Promise<AgentFleetSnapshot> {
    this.ensureCapacity();
    await Promise.all(this.supervisors.map(async (supervisor) => supervisor.runTick()));
    this.replaceBelowMinimum();
    await this.tickNonWorkingActiveAgents();
    this.replaceBelowMinimum();
    const snapshot = this.snapshot();
    this.emitMetrics(snapshot);
    return snapshot;
  }

  snapshot(): AgentFleetSnapshot {
    const snapshots = this.supervisors.map((s) => s.snapshot());
    const active = snapshots.filter((s) => this.isActive(s));
    const workingAgents = snapshots.filter((s) => this.isWorking(s)).length;
    const notWorkingAgents = this.desiredActiveAgents - workingAgents;
    return {
      desiredActiveAgents: this.desiredActiveAgents,
      totalAgents: this.supervisors.length,
      activeAgents: active.length,
      readyAgents: workingAgents,
      workingAgents,
      notWorkingAgents: Math.max(0, notWorkingAgents),
      allAgentsWorking: workingAgents >= this.desiredActiveAgents,
      warmingAgents: snapshots.filter((s) => s.status === "warming").length,
      degradedAgents: snapshots.filter((s) => s.status === "degraded").length,
      stoppedAgents: snapshots.filter((s) => s.status === "stopped").length,
    };
  }

  getSupervisors(): readonly AgentSupervisor[] {
    return this.supervisors;
  }

  private ensureCapacity(): void {
    while (this.activeCount() < this.desiredActiveAgents) {
      const supervisor = this.options.supervisorFactory(this.supervisors.length);
      supervisor.start();
      this.supervisors.push(supervisor);
    }

    while (this.activeCount() > this.maxActiveAgents) {
      const candidate = this.supervisors.find((s) => this.isActive(s.snapshot()));
      if (!candidate) return;
      candidate.stop("fleet over capacity");
    }
  }

  private async tickNonWorkingActiveAgents(): Promise<void> {
    const candidates = this.supervisors.filter((s) => {
      const snapshot = s.snapshot();
      return this.isActive(snapshot) && !this.isWorking(snapshot);
    });
    if (candidates.length === 0) return;
    await Promise.all(candidates.map(async (supervisor) => supervisor.runTick()));
  }

  private replaceBelowMinimum(): void {
    while (this.activeCount() < this.minActiveAgents) {
      const supervisor = this.options.supervisorFactory(this.supervisors.length);
      supervisor.start();
      this.supervisors.push(supervisor);
    }
  }

  private activeCount(): number {
    return this.supervisors.filter((s) => this.isActive(s.snapshot())).length;
  }

  private isActive(snapshot: AgentSupervisorSnapshot): boolean {
    return snapshot.started && snapshot.status !== "stopped" && snapshot.status !== "degraded";
  }

  private isWorking(snapshot: AgentSupervisorSnapshot): boolean {
    return snapshot.started && snapshot.status === "ready";
  }

  private emitMetrics(snapshot: AgentFleetSnapshot): void {
    this.metrics.histogram("agent_fleet_active_agents", snapshot.activeAgents, {
      component: "agent_fleet",
    });
    this.metrics.histogram("agent_fleet_ready_agents", snapshot.readyAgents, {
      component: "agent_fleet",
    });
    this.metrics.histogram("agent_fleet_working_agents", snapshot.workingAgents, {
      component: "agent_fleet",
    });
    this.metrics.histogram("agent_fleet_not_working_agents", snapshot.notWorkingAgents, {
      component: "agent_fleet",
    });
    this.metrics.histogram("agent_fleet_degraded_agents", snapshot.degradedAgents, {
      component: "agent_fleet",
    });
    if (snapshot.activeAgents < this.minActiveAgents) {
      this.metrics.counter("agent_fleet_below_min_total", 1, { component: "agent_fleet" });
    }
    if (snapshot.workingAgents < this.minWorkingAgents) {
      this.metrics.counter("agent_fleet_below_working_min_total", 1, { component: "agent_fleet" });
    }
  }

  private validatePolicy(): void {
    for (const [name, value] of Object.entries({
      desiredActiveAgents: this.desiredActiveAgents,
      minActiveAgents: this.minActiveAgents,
      maxActiveAgents: this.maxActiveAgents,
      minWorkingAgents: this.minWorkingAgents,
    })) {
      if (!Number.isInteger(value) || value < 1) {
        throw new Error(`${name} must be a positive integer`);
      }
    }
    if (this.minActiveAgents > this.desiredActiveAgents) {
      throw new Error("minActiveAgents cannot exceed desiredActiveAgents");
    }
    if (this.desiredActiveAgents > this.maxActiveAgents) {
      throw new Error("desiredActiveAgents cannot exceed maxActiveAgents");
    }
    if (this.minWorkingAgents > this.desiredActiveAgents) {
      throw new Error("minWorkingAgents cannot exceed desiredActiveAgents");
    }
  }
}
