import type { EnterpriseArchitectureIndex } from "./enterpriseArchitectureIndex";
import {
  PHASE_LABELS,
  contractLabel,
  deriveLifelines,
  isFragment,
  isResponsePhase,
  resolveStep,
  type Lifeline,
  type ScenarioDocument,
  type ScenarioFragmentKind,
  type ScenarioItem,
  type ScenarioPhase,
  type StepOutcome,
} from "./scenarioModel";

export const SEQUENCE_METRICS = {
  marginX: 40,
  lifelineGap: 220,
  headerHeight: 56,
  headerWidth: 160,
  topGap: 28,
  messageRow: 56,
  selfRow: 72,
  selfLoopWidth: 44,
  fragmentHeader: 26,
  operandGuard: 22,
  fragmentPadding: 14,
  fragmentNestInset: 10,
  bottomGap: 32,
} as const;

export type LayoutLifeline = Lifeline & { x: number };

export type LayoutMessage = {
  stepId: string;
  number: string;
  kind: "contract" | "self" | "actor";
  fromX: number;
  toX: number;
  y: number;
  self: boolean;
  dashed: boolean;
  label: string;
  detail: string | null;
  contractId: string | null;
  phase: ScenarioPhase | null;
  missing: string | null;
  status: string | null;
  outcome: StepOutcome | null;
};

export type LayoutOperand = { guard: string; y: number };

export type LayoutFragment = {
  id: string;
  kind: ScenarioFragmentKind;
  x: number;
  y: number;
  width: number;
  height: number;
  depth: number;
  operands: LayoutOperand[];
};

export type SequenceLayout = {
  width: number;
  height: number;
  lifelineTop: number;
  lifelineBottom: number;
  lifelines: LayoutLifeline[];
  messages: LayoutMessage[];
  fragments: LayoutFragment[];
};

type Span = { min: number; max: number; selfAtMax: boolean; nesting: number };

const EMPTY_SPAN: Span = { min: Number.POSITIVE_INFINITY, max: Number.NEGATIVE_INFINITY, selfAtMax: false, nesting: 0 };

function mergeSpan(a: Span, b: Span): Span {
  if (b.min > b.max) return { ...a, nesting: Math.max(a.nesting, b.nesting) };
  if (a.min > a.max) return b;
  const max = Math.max(a.max, b.max);
  return {
    min: Math.min(a.min, b.min),
    max,
    selfAtMax: (a.max === max && a.selfAtMax) || (b.max === max && b.selfAtMax),
    nesting: Math.max(a.nesting, b.nesting),
  };
}

export function layoutSequence(
  document: ScenarioDocument,
  index: EnterpriseArchitectureIndex | null,
  outcomes: ReadonlyMap<string, StepOutcome> = new Map(),
): SequenceLayout {
  const m = SEQUENCE_METRICS;
  const lifelines = deriveLifelines(document, index);
  const placed: LayoutLifeline[] = lifelines.map((lifeline, position) => ({
    ...lifeline,
    x: m.marginX + m.headerWidth / 2 + position * m.lifelineGap,
  }));
  const positionById = new Map(placed.map((item, position) => [item.id, position]));
  const messages: LayoutMessage[] = [];
  const fragments: LayoutFragment[] = [];
  let y = m.headerHeight + m.topGap;
  let stepNumber = 0;

  const walk = (items: readonly ScenarioItem[], depth: number): Span => {
    let span = EMPTY_SPAN;
    for (const item of items) {
      if (isFragment(item)) {
        const top = y;
        y += m.fragmentHeader;
        const operands: LayoutOperand[] = [];
        let inner = EMPTY_SPAN;
        item.operands.forEach((operand, operandIndex) => {
          if (operandIndex > 0) y += 6;
          operands.push({ guard: operand.guard, y });
          y += m.operandGuard;
          inner = mergeSpan(inner, walk(operand.items, depth + 1));
          if (operand.items.length === 0) y += m.messageRow / 2;
        });
        y += m.fragmentPadding;
        if (inner.min > inner.max) {
          inner = { min: 0, max: Math.max(placed.length - 1, 0), selfAtMax: false, nesting: inner.nesting };
        }
        const inset = m.fragmentPadding + inner.nesting * m.fragmentNestInset;
        const minX = (placed[inner.min]?.x ?? m.marginX + m.headerWidth / 2) - m.headerWidth / 2 + 20 - inset;
        const maxBase = placed[inner.max]?.x ?? minX + m.headerWidth;
        const maxX = Math.max(
          maxBase + (inner.selfAtMax ? m.selfLoopWidth + 70 : 0) + m.headerWidth / 2 - 20 + inset,
          minX + 200,
        );
        fragments.push({
          id: item.id,
          kind: item.kind,
          x: minX,
          y: top,
          width: maxX - minX,
          height: y - top,
          depth,
          operands,
        });
        y += 8;
        span = mergeSpan(span, { ...inner, nesting: inner.nesting + 1 });
        continue;
      }
      stepNumber += 1;
      const resolved = resolveStep(item, placed, index);
      const fromPos = resolved.fromLifelineId ? positionById.get(resolved.fromLifelineId) : undefined;
      const toPos = resolved.toLifelineId ? positionById.get(resolved.toLifelineId) : undefined;
      const self = item.kind === "self" || (fromPos !== undefined && fromPos === toPos);
      const fallbackX = placed[0]?.x ?? m.marginX + m.headerWidth / 2;
      const fromX = fromPos !== undefined ? placed[fromPos]!.x : fallbackX;
      const toX = toPos !== undefined ? placed[toPos]!.x : fromX;
      const phaseLabel = item.phase ? PHASE_LABELS[item.phase] : null;
      const isContract = item.kind === "contract";
      messages.push({
        stepId: item.id,
        number: String(stepNumber),
        kind: item.kind,
        fromX,
        toX,
        y: y + (self ? 14 : 22),
        self,
        dashed: isContract && isResponsePhase(item.phase),
        label: isContract ? `${contractLabel(index, item.contractId)} · ${phaseLabel}` : item.label?.trim() || "Message",
        detail: isContract ? item.label?.trim() || null : null,
        contractId: isContract ? item.contractId ?? null : null,
        phase: isContract ? item.phase ?? null : null,
        missing: resolved.missing,
        status: resolved.endpoints?.phase?.validationSummary.status ?? null,
        outcome: outcomes.get(item.id) ?? null,
      });
      y += self ? m.selfRow : m.messageRow;
      const positions = [fromPos, toPos].filter((value): value is number => value !== undefined);
      if (positions.length) {
        const min = Math.min(...positions);
        const max = Math.max(...positions);
        span = mergeSpan(span, { min, max, selfAtMax: self, nesting: 0 });
      }
    }
    return span;
  };

  walk(document.items, 0);
  const lifelineBottom = Math.max(y + m.bottomGap, m.headerHeight + m.topGap + 80);
  const contentRight = Math.max(
    placed.length ? placed[placed.length - 1]!.x + m.headerWidth / 2 : 0,
    ...fragments.map((fragment) => fragment.x + fragment.width),
    ...messages.filter((message) => message.self).map((message) => message.fromX + m.selfLoopWidth + 160),
  );
  return {
    width: Math.max(contentRight + m.marginX, 480),
    height: lifelineBottom + 16,
    lifelineTop: m.headerHeight,
    lifelineBottom,
    lifelines: placed,
    messages,
    fragments: fragments.sort((a, b) => a.depth - b.depth),
  };
}
