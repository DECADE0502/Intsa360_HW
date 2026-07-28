import { Button, Tag } from "antd";
import {
  ArrowRight,
  Braces,
  GitBranch,
  ListChecks,
  ShieldAlert,
} from "lucide-react";
import type { SemanticCompare } from "./types";
import { summarizeCompare } from "./summary";

function signed(value: number) {
  return value > 0 ? `+${value}` : String(value);
}

export function CompareOverview({
  semantic,
  onNavigate,
}: {
  semantic: SemanticCompare;
  onNavigate: (key: string) => void;
}) {
  const view = summarizeCompare(semantic);
  const summary = semantic.summary;
  return (
    <div className="bom-overview">
      <ol className="bom-review-route">
        <li>
          <div className="bom-review-route-icon"><ListChecks size={19} /></div>
          <div>
            <span>第一步 · 核对贴装</span>
            <strong>
              {view.placementGroupCount} 组相同变化，涉及 {view.placementReferenceCount} 个位号
            </strong>
            <p>
              主料变化 {view.placement.migrated} 组，新增 {view.placement.added} 组，
              移除 {view.placement.removed} 组。整板实际位号
              {" "}{summary.actual_reference_count_old} → {summary.actual_reference_count_new}
              （{signed(view.referenceDelta)}）。
            </p>
          </div>
          <Button type="link" onClick={() => onNavigate("placement")}>
            查看位号 <ArrowRight size={15} />
          </Button>
        </li>
        <li>
          <div className="bom-review-route-icon"><GitBranch size={19} /></div>
          <div>
            <span>第二步 · 核对替代关系</span>
            <strong>{semantic.substitute_diff.length} 个替代组发生变化</strong>
            <p>
              新增 {view.substitute.added}，调整 {view.substitute.changed}，
              删除 {view.substitute.removed}。替代料数量不会重复计入整板贴装数量。
            </p>
          </div>
          <Button type="link" onClick={() => onNavigate("substitute")}>
            查看替代组 <ArrowRight size={15} />
          </Button>
        </li>
        <li>
          <div className="bom-review-route-icon"><Braces size={19} /></div>
          <div>
            <span>第三步 · 区分非装配字段</span>
            <strong>{view.metadataFieldCount} 个非装配字段变化</strong>
            <p>
              覆盖 {view.metadataChangeCount} 条板级或物料记录，单独列示，不直接判定为贴错风险；例如描述、备注、发料方式和板级信息。
            </p>
          </div>
          <Button type="link" onClick={() => onNavigate("details")}>
            查看字段 <ArrowRight size={15} />
          </Button>
        </li>
        <li className={view.blockingRecordCount ? "is-blocked" : "is-clear"}>
          <div className="bom-review-route-icon"><ShieldAlert size={19} /></div>
          <div>
            <span>第四步 · 处理质量门禁</span>
            <strong>
              {view.blockingRecordCount
                ? `${view.blockingRecordCount} 条源记录需要处理`
                : "没有阻断项"}
            </strong>
            <p>
              {view.blockingRecordCount
                ? `共 ${semantic.blockers.length} 个字段或结构问题；修复前不能生成正式 PLM / OA。`
                : semantic.warnings.length
                  ? `仍有 ${semantic.warnings.length} 条警告，建议交付前确认。`
                  : "当前结果通过结构校验，可以继续查看和导出交付文件。"}
            </p>
          </div>
          <Button type="link" danger={Boolean(view.blockingRecordCount)} onClick={() => onNavigate("delivery")}>
            {view.blockingRecordCount ? "处理阻断" : "查看交付"} <ArrowRight size={15} />
          </Button>
        </li>
      </ol>
      <div className="bom-overview-footnote">
        <Tag color="blue">需复核事件 {view.reviewEventCount}</Tag>
        <Tag>元数据事件 {view.metadataEventCount}</Tag>
        <span>事件是归并后的业务说明，数量与“位号差异”不是同一统计层级。</span>
      </div>
    </div>
  );
}
