import test from "node:test";
import assert from "node:assert/strict";
import { interactionIcon, interactionDescribe, eventDescribe } from "./timelineRender.ts";

test("interaction icon: interview vs outgoing vs incoming", () => {
  assert.equal(interactionIcon({ channel: "interview", direction: "out" }), "🎤");
  assert.equal(interactionIcon({ channel: "mail", direction: "out" }), "→");
  assert.equal(interactionIcon({ channel: "mail", direction: "in" }), "←");
});

test("interaction describe: interview uses stage label", () => {
  assert.equal(
    interactionDescribe({ channel: "interview", direction: "in", subject: null, interview_stage: "technical" }),
    "Interview — Technical",
  );
});

test("interaction describe: mail uses direction verb + subject", () => {
  assert.equal(
    interactionDescribe({ channel: "mail", direction: "out", subject: "Hello", interview_stage: null }),
    "Sent via mail — Hello",
  );
});

test("event describe: status change renders from -> to", () => {
  assert.equal(eventDescribe({ kind: "status_change", from: "draft", to: "applied" }), "Status: draft → applied");
});
