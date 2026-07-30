import { useMemo, useState } from "react";
import {
  Button,
  Input,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { SearchOutlined } from "@ant-design/icons";

import { SmtBoardViewport } from "../../components/SmtBoardViewport";
import type { PlacementDecisionInput } from "./api";
import { DecisionBar } from "./DecisionBar";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { SMT_STATE_LABELS } from "./labels";
import { SmtPlacementVirtualList } from "./SmtPlacementVirtualList";
import type {
  SmtAnalysisRunResponse,
  SmtAssemblyState,
  SmtPlacement,
} from "./types";
import styles from "./SmtAnalysisPane.module.css";


const ACTIONABLE = new Set<SmtAssemblyState>([
  "candidate_nc",
  "bom_only",
  "coordinate_only",
  "conflicting",
  "unresolved",
]);

function naturalCompare(left: string, right: string) {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

export function ReviewWorkbench({
  run,
  busy,
  onDecide,
  onBatchDecide,
  onComplete,
}: {
  run: SmtAnalysisRunResponse;
  busy: boolean;
  onDecide: (
    placementId: string,
    input: PlacementDecisionInput,
  ) => Promise<void>;
  onBatchDecide: (
    placementIds: string[],
    input: PlacementDecisionInput,
  ) => Promise<void>;
  onComplete: () => Promise<void>;
}) {
  const [scope, setScope] = useState<"actionable" | "all">("actionable");
  const [side, setSide] = useState<"all" | "top" | "bottom">("all");
  const [boardSide, setBoardSide] = useState<"top" | "bottom">(
    run.registrations.find(
      (item) =>
        item.side === "top" || item.side === "bottom",
    )?.side as "top" | "bottom" || "top",
  );
  const [state, setState] = useState<SmtAssemblyState | "all">("all");
  const [search, setSearch] = useState("");
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [selectedRef, setSelectedRef] = useState(
    run.placements.find((item) => ACTIONABLE.has(item.assembly_state))?.ref ||
      run.placements[0]?.ref ||
      "",
  );
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const filtered = useMemo(
    () =>
      run.placements
        .filter((item) => scope === "all" || ACTIONABLE.has(item.assembly_state))
        .filter((item) => side === "all" || item.side === side)
        .filter((item) => state === "all" || item.assembly_state === state)
        .filter((item) => {
          const query = search.trim().toUpperCase();
          if (!query) return true;
          const materials =
            item.bom_requirement?.materials
              .map((candidate) => candidate.part_number)
              .join(" ") || "";
          return `${item.ref} ${materials}`.toUpperCase().includes(query);
        })
        .sort(
          (left, right) =>
            Number(ACTIONABLE.has(right.assembly_state)) -
              Number(ACTIONABLE.has(left.assembly_state)) ||
            naturalCompare(left.ref, right.ref),
        ),
    [run.placements, scope, side, state, search],
  );
  const selected =
    run.placements.find((item) => item.ref === selectedRef) || filtered[0];
  const selectedIds = new Set(
    Array.from(checked).filter((identifier) =>
      filtered.some((item) => item.placement_id === identifier),
    ),
  );
  const highlightedRefs = useMemo(
    () =>
      search.trim() ||
      scope === "actionable" ||
      side !== "all" ||
      state !== "all"
        ? new Set(filtered.map((item) => item.ref))
        : new Set<string>(),
    [filtered, scope, search, side, state],
  );

  async function decideOne(input: PlacementDecisionInput) {
    if (!selected) return;
    await onDecide(selected.placement_id, input);
  }

  async function decideBatch(input: PlacementDecisionInput) {
    await onBatchDecide(Array.from(selectedIds), input);
    setChecked(new Set());
  }

  return (
    <div>
      <div className={styles.summaryStrip}>
        {[
          ["总位号", run.summary.placement_count],
          ["已装机", run.summary.installed_count],
          ["确认 NC", run.summary.confirmed_nc_count],
          ["候选 NC", run.summary.candidate_nc_count],
          ["待解决", run.summary.unresolved_count],
        ].map(([label, value]) => (
          <div className={styles.summaryItem} key={String(label)}>
            <span className={styles.summaryValue}>{value}</span>
            <Typography.Text type="secondary">{label}</Typography.Text>
          </div>
        ))}
      </div>
      <div className={styles.configurationBar} style={{ marginTop: 0 }}>
        <Space wrap>
          <Segmented
            value={scope}
            options={[
              { label: "只看异常", value: "actionable" },
              { label: "全部器件", value: "all" },
            ]}
            onChange={(value) => setScope(value as "actionable" | "all")}
          />
          <Segmented
            value={side}
            options={[
              { label: "全部面", value: "all" },
              { label: "正面", value: "top" },
              { label: "背面", value: "bottom" },
            ]}
            onChange={(value) => {
              const next = value as "all" | "top" | "bottom";
              setSide(next);
              if (next !== "all") setBoardSide(next);
            }}
          />
          <Select
            aria-label="装机状态筛选"
            value={state}
            style={{ width: 170 }}
            options={[
              { value: "all", label: "全部状态" },
              ...Object.entries(SMT_STATE_LABELS).map(([value, label]) => ({
                value,
                label,
              })),
            ]}
            onChange={(value) => setState(value as SmtAssemblyState | "all")}
          />
        </Space>
        <Space>
          <Typography.Text type="secondary">
            当前 {filtered.length} / {run.placements.length} 项
          </Typography.Text>
          <Button
            type="primary"
            loading={busy}
            disabled={run.summary.unresolved_count > 0}
            onClick={onComplete}
          >
            完成复核
          </Button>
        </Space>
      </div>

      <div
        className={styles.reviewShell}
        data-evidence-open={evidenceOpen}
      >
        <div className={styles.reviewLayout}>
          <section className={styles.viewportPanel}>
            <SmtBoardViewport
              run={run}
              side={boardSide}
              selectedRef={selected?.ref}
              highlightedRefs={highlightedRefs}
              onSideChange={setBoardSide}
              onSelect={(placement: SmtPlacement) => {
                setSelectedRef(placement.ref);
                if (
                  placement.side === "top" ||
                  placement.side === "bottom"
                ) {
                  setBoardSide(placement.side);
                }
                setEvidenceOpen(true);
              }}
            />
          </section>

          <section className={styles.reviewList}>
            <div className={styles.panelHeader}>
              <Typography.Text strong>位号与异常</Typography.Text>
              <Tag>{filtered.length}</Tag>
            </div>
            <div className={styles.reviewSearch}>
              <Input
                allowClear
                prefix={<SearchOutlined />}
                aria-label="搜索位号或料号"
                placeholder="搜索位号或料号"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <SmtPlacementVirtualList
              items={filtered}
              selectedRef={selected?.ref}
              selectedIds={selectedIds}
              onSelect={(placement) => {
                setSelectedRef(placement.ref);
                if (
                  placement.side === "top" ||
                  placement.side === "bottom"
                ) {
                  setBoardSide(placement.side);
                }
                setEvidenceOpen(true);
              }}
              onCheck={(placementId, enabled) => {
                setChecked((current) => {
                  const next = new Set(current);
                  if (enabled) {
                    next.add(placementId);
                  } else {
                    next.delete(placementId);
                  }
                  return next;
                });
              }}
            />
            <DecisionBar
              visible={filtered}
              selected={selectedIds}
              busy={busy}
              onSelectAll={(enabled) =>
                setChecked(
                  enabled
                    ? new Set(
                        filtered.map((item) => item.placement_id),
                      )
                    : new Set(),
                )
              }
              onApply={decideBatch}
            />
          </section>
        </div>
        <EvidenceDrawer
          placement={selected}
          busy={busy}
          open={evidenceOpen}
          onToggle={() => setEvidenceOpen((current) => !current)}
          onDecide={decideOne}
        />
      </div>
    </div>
  );
}
