import {
  Button,
  Descriptions,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import {
  DownOutlined,
  UpOutlined,
} from "@ant-design/icons";

import type { PlacementDecisionInput } from "./api";
import {
  SMT_EVIDENCE_KIND_LABELS,
  SMT_ROLE_LABELS,
  SMT_STATE_LABELS,
} from "./labels";
import type {
  SmtPlacement,
  SmtPlacementRole,
} from "./types";
import styles from "./SmtAnalysisPane.module.css";


const ROLE_OPTIONS = (
  Object.entries(SMT_ROLE_LABELS) as Array<
    [SmtPlacementRole, string]
  >
).map(([value, label]) => ({ value, label }));

export function EvidenceDrawer({
  placement,
  busy,
  open,
  onToggle,
  onDecide,
}: {
  placement?: SmtPlacement;
  busy: boolean;
  open: boolean;
  onToggle: () => void;
  onDecide: (input: PlacementDecisionInput) => void;
}) {
  const primary = placement?.bom_requirement?.materials.find(
    (item) => item.is_primary,
  );
  return (
    <section className={styles.evidenceDock} data-open={open}>
      <div className={styles.evidenceDockHeader}>
        <Space size={8}>
          <Typography.Text strong>证据与决策</Typography.Text>
          {placement ? (
            <>
              <Typography.Text strong>{placement.ref}</Typography.Text>
              <Tag
                color={
                  placement.blocking_reasons.length ? "red" : "blue"
                }
              >
                {SMT_STATE_LABELS[placement.assembly_state]}
              </Tag>
              <Typography.Text type="secondary">
                {primary?.part_number || "无 BOM 料号"}
              </Typography.Text>
            </>
          ) : (
            <Typography.Text type="secondary">
              选择一个位号查看完整证据
            </Typography.Text>
          )}
        </Space>
        <Button
          type="text"
          disabled={!placement}
          icon={open ? <DownOutlined /> : <UpOutlined />}
          onClick={onToggle}
        >
          {open ? "收起证据" : "展开证据"}
        </Button>
      </div>
      {open && placement ? (
        <div className={styles.evidenceDockBody}>
          <div className={styles.evidenceColumn}>
            <Typography.Text strong>位号信息</Typography.Text>
            <Descriptions
              size="small"
              column={1}
              labelStyle={{ width: 80 }}
              items={[
                {
                  key: "side",
                  label: "板面",
                  children:
                    placement.side === "bottom"
                      ? "背面"
                      : placement.side === "top"
                        ? "正面"
                        : "待确认",
                },
                {
                  key: "part",
                  label: "主料编码",
                  children: primary?.part_number || "无",
                },
                {
                  key: "role",
                  label: "器件角色",
                  children: SMT_ROLE_LABELS[placement.role],
                },
                {
                  key: "coordinate",
                  label: "坐标记录",
                  children: placement.coordinate_occurrence_ids.length
                    ? `${placement.coordinate_occurrence_ids.length} 条`
                    : "无",
                },
                {
                  key: "netlist",
                  label: "网表",
                  children:
                    placement.netlist_present == null
                      ? "未提供"
                      : placement.netlist_present
                        ? "存在"
                        : "不存在",
                },
              ]}
            />
          </div>
          <div className={styles.evidenceColumn}>
            <Typography.Text strong>
              {placement.blocking_reasons.length
                ? "阻断原因与证据"
                : "判定证据"}
            </Typography.Text>
            <div className={styles.evidenceScroll}>
              {placement.blocking_reasons.map((reason) => (
                <Typography.Paragraph
                  key={reason}
                  type="danger"
                  className={styles.evidenceReason}
                >
                  {reason}
                </Typography.Paragraph>
              ))}
              <Space
                direction="vertical"
                size={8}
                style={{ width: "100%" }}
              >
                {placement.evidence_chain.map((item, index) => (
                  <div key={`${item.kind}-${index}`}>
                    <Space size={6}>
                      <Tag
                        color={
                          item.weight === "conflicting"
                            ? "red"
                            : item.weight === "strong"
                              ? "green"
                              : item.weight === "supporting"
                                ? "blue"
                                : "default"
                        }
                      >
                        {item.weight === "strong"
                          ? "强证据"
                          : item.weight === "supporting"
                            ? "辅助证据"
                            : item.weight === "conflicting"
                              ? "冲突"
                              : "弱证据"}
                      </Tag>
                      <Typography.Text type="secondary">
                        {SMT_EVIDENCE_KIND_LABELS[item.kind] ||
                          "其他证据"}
                      </Typography.Text>
                    </Space>
                    <Typography.Paragraph
                      className={styles.evidenceMessage}
                    >
                      {item.message}
                    </Typography.Paragraph>
                  </div>
                ))}
              </Space>
            </div>
          </div>
          <div className={styles.evidenceColumn}>
            <Typography.Text strong>人工决策</Typography.Text>
            <Select
              aria-label="器件角色"
              value={placement.role}
              style={{ width: "100%" }}
              options={ROLE_OPTIONS}
              onChange={(role) =>
                onDecide({
                  action: "change_role",
                  role,
                  reason: "人工修正角色",
                })
              }
            />
            <div className={styles.evidenceActions}>
              <Button
                type="primary"
                loading={busy}
                onClick={() =>
                  onDecide({
                    action: "confirm_installed",
                    role: placement.role,
                    reason: "人工确认装机",
                  })
                }
              >
                确认为装机
              </Button>
              <Button
                danger
                loading={busy}
                onClick={() =>
                  onDecide({
                    action: "confirm_nc",
                    role: placement.role,
                    reason: "人工确认 NC",
                  })
                }
              >
                确认为 NC
              </Button>
              <Button
                loading={busy}
                onClick={() =>
                  onDecide({
                    action: "mark_process",
                    role: placement.role,
                    reason: "人工确认为工艺对象",
                  })
                }
              >
                标记工艺项
              </Button>
              <Button
                loading={busy}
                onClick={() =>
                  onDecide({
                    action: "mark_non_smt",
                    role: placement.role,
                    reason: "人工确认为非 SMT",
                  })
                }
              >
                标记非 SMT
              </Button>
            </div>
            {placement.decision ? (
              <Typography.Paragraph
                type="secondary"
                className={styles.latestDecision}
              >
                最近决策：
                {placement.decision.reason ||
                  placement.decision.action}
              </Typography.Paragraph>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
