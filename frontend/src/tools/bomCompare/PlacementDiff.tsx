import { useEffect, useMemo, useState } from "react";
import { Empty, Input, Segmented, Tag } from "antd";
import { ArrowRight, Search } from "lucide-react";
import type { ChangeEvent, PlacementDiff as PlacementDiffType } from "./types";
import { changeKindLabels } from "./types";

const statusLabels = {
  migrated: { label: "主料变化", color: "red" },
  added: { label: "新增位号", color: "blue" },
  removed: { label: "移除位号", color: "orange" },
};

function materialDescription(
  events: ChangeEvent[],
  side: "old_snapshot" | "new_snapshot",
  materialCode: string,
) {
  if (!materialCode) return "";
  for (const event of events) {
    const snapshot = event[side];
    if (snapshot?.material_code !== materialCode) continue;
    const variants = Array.isArray(snapshot.variants) ? snapshot.variants : [];
    const variant = variants[0] as Record<string, unknown> | undefined;
    const description = variant?.description || variant?.model || variant?.name;
    if (description) return String(description);
  }
  return "";
}

export function PlacementDiff({
  rows,
  events,
  selectedReference,
  onSelectedReference,
}: {
  rows: PlacementDiffType[];
  events: ChangeEvent[];
  selectedReference: string;
  onSelectedReference: (reference: string) => void;
}) {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return rows.filter((row) => {
      const matchesFilter = filter === "all" || row.status === filter;
      const haystack = `${row.parent_code} ${row.reference} ${row.old_material_code} ${row.new_material_code}`.toLowerCase();
      return matchesFilter && (!normalized || haystack.includes(normalized));
    });
  }, [filter, query, rows]);
  const selected = rows.find((row) => row.reference === selectedReference) || filtered[0];
  const related = selected
    ? events.filter(
      (event) => event.impact !== "metadata" && event.references?.includes(selected.reference),
    )
    : [];
  const oldDescription = selected
    ? materialDescription(related, "old_snapshot", selected.old_material_code)
    : "";
  const newDescription = selected
    ? materialDescription(related, "new_snapshot", selected.new_material_code)
    : "";

  useEffect(() => {
    if (selected && selected.reference !== selectedReference) {
      onSelectedReference(selected.reference);
    }
  }, [selected?.reference, selectedReference]);

  if (!rows.length) {
    return <Empty description="实际贴装位号没有变化" />;
  }

  return (
    <div className="bom-placement-workbench">
      <aside className="bom-diff-rail">
        <Segmented
          block
          value={filter}
          onChange={(value) => setFilter(String(value))}
          options={[
            { label: `全部 ${rows.length}`, value: "all" },
            { label: "主料变化", value: "migrated" },
            { label: "新增", value: "added" },
            { label: "移除", value: "removed" },
          ]}
        />
        <Input
          allowClear
          prefix={<Search size={15} />}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索位号或物料编码"
        />
        <div className="bom-diff-list" role="listbox" aria-label="贴装差异">
          {filtered.map((row) => (
            <button
              type="button"
              key={`${row.parent_code}:${row.reference}`}
              className={`bom-diff-list-item ${selected?.reference === row.reference ? "is-active" : ""}`}
              onClick={() => onSelectedReference(row.reference)}
            >
              <span className="bom-reference">{row.reference}</span>
              <Tag color={statusLabels[row.status].color}>{statusLabels[row.status].label}</Tag>
              <small>{row.parent_code}</small>
            </button>
          ))}
        </div>
      </aside>

      <section className="bom-placement-detail" key={selected?.reference}>
        {selected ? (
          <>
            <div className="bom-detail-title">
              <div>
                <span className="bom-kicker">实际贴装位号</span>
                <h3>{selected.reference}</h3>
              </div>
              <Tag color={statusLabels[selected.status].color}>{statusLabels[selected.status].label}</Tag>
            </div>
            <div className="bom-material-transition">
              <div>
                <span>旧版主料</span>
                <strong>{selected.old_material_code || "无"}</strong>
                {oldDescription ? <p>{oldDescription}</p> : null}
              </div>
              <ArrowRight aria-hidden size={20} />
              <div>
                <span>新版主料</span>
                <strong>{selected.new_material_code || "无"}</strong>
                {newDescription ? <p>{newDescription}</p> : null}
              </div>
            </div>
            <dl className="bom-evidence-list">
              <div><dt>父项</dt><dd>{selected.parent_code}</dd></div>
              <div><dt>判定层</dt><dd>主料实际位号</dd></div>
              <div><dt>统计口径</dt><dd>只按主料实际位号计数，替代料不重复累加</dd></div>
            </dl>
          </>
        ) : null}
      </section>

      <aside className="bom-event-inspector">
        <span className="bom-kicker">关联业务事件</span>
        {related.length ? related.map((event) => (
          <article key={event.event_id} className={`bom-event-note is-${event.impact}`}>
            <Tag>{changeKindLabels[event.kind] || event.kind}</Tag>
            <strong>{event.title}</strong>
            {event.oa_change_type ? <p>OA 类型：{event.oa_change_type}</p> : null}
            {event.group_codes?.length ? <p>替代组：{event.group_codes.join(" / ")}</p> : null}
          </article>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无额外业务事件" />}
      </aside>
    </div>
  );
}
