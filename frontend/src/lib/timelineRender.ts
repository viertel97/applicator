import { STAGE_LABEL } from "./interviewSummary.ts";
import type { Channel, Direction, InterviewStage } from "../api/interactions.ts";

type InteractionLike = {
  channel: Channel | string;
  direction: Direction | string;
};

type InteractionDescribeLike = InteractionLike & {
  subject: string | null;
  interview_stage: InterviewStage | string | null;
};

type EventLike = { kind: string; from: string | null; to: string | null };

export function interactionIcon(it: InteractionLike): string {
  if (it.channel === "interview") return "🎤";
  return it.direction === "out" ? "→" : "←";
}

export function interactionDescribe(it: InteractionDescribeLike): string {
  if (it.channel === "interview") {
    const stage = it.interview_stage
      ? STAGE_LABEL[it.interview_stage as InterviewStage]
      : null;
    const tail = stage ?? it.subject;
    return `Interview${tail ? ` — ${tail}` : ""}`;
  }
  const dir = it.direction === "out" ? "Sent" : "Received";
  return `${dir} via ${it.channel}${it.subject ? ` — ${it.subject}` : ""}`;
}

export function eventDescribe(ev: EventLike): string {
  if (ev.kind === "status_change") return `Status: ${ev.from} → ${ev.to}`;
  return ev.kind;
}
