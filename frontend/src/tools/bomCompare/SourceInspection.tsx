import { Alert, Tag, Tooltip } from "antd";
import { CircleCheck, CircleX, Layers3, PackageSearch } from "lucide-react";
import type { SourceInspectionPayload } from "./types";
import { profileLabels } from "./types";

export function SourceInspection({
  label,
  inspection,
}: {
  label: string;
  inspection?: SourceInspectionPayload;
}) {
  if (!inspection) return null;
  const placements = inspection.boards.reduce(
    (sum, board) => sum + (board.placement_count ?? board.placements?.length ?? 0),
    0,
  );
  const groups = inspection.boards.reduce(
    (sum, board) => sum + (board.substitute_group_count ?? board.substitute_groups?.length ?? 0),
    0,
  );
  const blockers = inspection.findings.filter((finding) => finding.severity === "blocker");
  const warnings = inspection.findings.filter((finding) => finding.severity === "warning");

  return (
    <section className="bom-source-inspection" aria-label={`${label}来源体检`}>
      <div className="bom-source-inspection-head">
        <div>
          <span className="bom-kicker">{label}</span>
          <strong>{profileLabels[inspection.envelope.profile] || inspection.envelope.profile}</strong>
        </div>
        <Tag
          icon={inspection.can_compare ? <CircleCheck size={13} /> : <CircleX size={13} />}
          color={inspection.can_compare ? "success" : "error"}
        >
          {inspection.can_compare ? "可比较" : "需先处理"}
        </Tag>
      </div>
      <div className="bom-source-facts">
        <Tooltip title="父项数量">
          <span><Layers3 size={14} /> {inspection.boards.length} 个父项</span>
        </Tooltip>
        <Tooltip title="主料实际贴装位号数量">
          <span><PackageSearch size={14} /> {placements} 个位号</span>
        </Tooltip>
        <span>{groups} 个替代组</span>
        <span>{blockers.length} 个阻断</span>
        {warnings.length ? <span>{warnings.length} 个警告</span> : null}
      </div>
      <div className="bom-board-tags">
        {inspection.boards.map((board) => (
          <Tag key={board.parent_code}>
            {board.parent_code}
            {board.hardware_version ? ` · ${board.hardware_version}` : ""}
          </Tag>
        ))}
      </div>
      {blockers.length ? (
        <Alert
          type="error"
          showIcon
          message={blockers[0].message}
          description={blockers.length > 1 ? `另有 ${blockers.length - 1} 个阻断项，请在“风险与交付”中查看。` : undefined}
        />
      ) : null}
    </section>
  );
}
