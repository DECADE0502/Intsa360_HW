import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Radio,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import {
  CheckCircleOutlined,
  FileImageOutlined,
  TableOutlined,
} from "@ant-design/icons";

import type { SourceConfirmationInput } from "./api";
import type {
  SmtAnalysisRunResponse,
  SmtBoardSide,
  SmtCoordinateScope,
} from "./types";
import styles from "./SmtAnalysisPane.module.css";


type IdentificationStepProps = {
  run: SmtAnalysisRunResponse;
  busy: boolean;
  error: string;
  onConfirm: (input: SourceConfirmationInput) => void;
};

const SCOPE_OPTIONS: Array<{
  value: SmtCoordinateScope;
  label: string;
  description: string;
}> = [
  {
    value: "unknown",
    label: "范围未知",
    description: "坐标减 BOM 仅形成候选 NC，需人工确认。",
  },
  {
    value: "full_design_set",
    label: "完整设计位号",
    description: "坐标包含设计中全部物理位号，可用于确认 NC。",
  },
  {
    value: "placement_only",
    label: "实际贴装位号",
    description: "坐标仅含本次上件对象，不能由差集推断 NC。",
  },
  {
    value: "smt_only",
    label: "仅 SMT 范围",
    description: "坐标不含插件/手工件，差异需单独复核。",
  },
];

function roleCount(run: SmtAnalysisRunResponse, role: string) {
  return run.sources.filter((source) => source.roles.includes(role as never)).length;
}

function pageDefault(run: SmtAnalysisRunResponse) {
  const result: Record<string, SmtBoardSide> = {};
  const used = new Set<SmtBoardSide>();
  run.drawing_pages.forEach((page) => {
    if (
      (page.side_candidate === "top" || page.side_candidate === "bottom") &&
      !used.has(page.side_candidate)
    ) {
      result[page.page_id] = page.side_candidate;
      used.add(page.side_candidate);
    }
  });
  return result;
}

export function IdentificationStep({
  run,
  busy,
  error,
  onConfirm,
}: IdentificationStepProps) {
  const [coordinateSetId, setCoordinateSetId] = useState(
    run.coordinate_sets.length === 1
      ? run.coordinate_sets[0].coordinate_set_id
      : "",
  );
  const [scope, setScope] = useState<SmtCoordinateScope>("unknown");
  const [pages, setPages] = useState<Record<string, SmtBoardSide>>(() =>
    pageDefault(run),
  );
  const selectedSet = useMemo(
    () =>
      run.coordinate_sets.find(
        (item) => item.coordinate_set_id === coordinateSetId,
      ),
    [coordinateSetId, run.coordinate_sets],
  );
  const [unit, setUnit] = useState<"mm" | "mil" | "inch" | undefined>(
    selectedSet?.normalized_unit || undefined,
  );

  useEffect(() => {
    if (!selectedSet) return;
    setUnit(selectedSet.normalized_unit || undefined);
  }, [selectedSet]);

  const sourceById = useMemo(
    () => new Map(run.sources.map((source) => [source.asset_id, source])),
    [run.sources],
  );
  const chosenSides = Object.values(pages);
  const duplicateSide =
    chosenSides.filter((side) => side === "top").length > 1 ||
    chosenSides.filter((side) => side === "bottom").length > 1;
  const canContinue =
    Boolean(selectedSet) &&
    !duplicateSide &&
    (!run.drawing_pages.length || chosenSides.length > 0) &&
    (selectedSet?.unit_state !== "unknown" || Boolean(unit));

  return (
    <div>
      <div className={styles.summaryStrip}>
        {[
          ["资料文件", run.sources.length],
          ["坐标候选", run.coordinate_sets.length],
          ["位号图页面", run.drawing_pages.length],
          ["BOM 装机位号", run.summary.installed_count],
          ["待确认问题", run.summary.blocking_count],
        ].map(([label, value]) => (
          <div className={styles.summaryItem} key={String(label)}>
            <span className={styles.summaryValue}>{value}</span>
            <Typography.Text type="secondary">{label}</Typography.Text>
          </div>
        ))}
      </div>

      {run.blocking_reasons.length ? (
        <Alert
          type="warning"
          showIcon
          message="资料需要确认"
          description={run.blocking_reasons.join("；")}
          style={{ marginBottom: 12 }}
        />
      ) : null}

      <div className={styles.candidateLayout}>
        <section className={styles.candidatePanel}>
          <div className={styles.panelHeader}>
            <Space>
              <TableOutlined />
              <Typography.Text strong>坐标数据</Typography.Text>
            </Space>
            <Tag>{run.coordinate_sets.length} 个候选</Tag>
          </div>
          <div className={styles.coordinateList}>
            {run.coordinate_sets.map((candidate) => {
              const source = sourceById.get(candidate.source_asset_id);
              return (
                <label
                  className={styles.coordinateOption}
                  data-selected={
                    candidate.coordinate_set_id === coordinateSetId
                  }
                  key={candidate.coordinate_set_id}
                >
                  <Radio
                    checked={candidate.coordinate_set_id === coordinateSetId}
                    onChange={() =>
                      setCoordinateSetId(candidate.coordinate_set_id)
                    }
                  />
                  <span>
                    <Typography.Text strong ellipsis>
                      {source?.relative_path || candidate.sheet_or_section}
                    </Typography.Text>
                    <br />
                    <Typography.Text type="secondary">
                      {candidate.quality_report.valid_rows} 个位号
                      {candidate.sheet_or_section
                        ? ` · ${candidate.sheet_or_section}`
                        : ""}
                    </Typography.Text>
                  </span>
                  <Tag
                    color={
                      candidate.quality_report.issues.some(
                        (issue) => issue.severity === "blocking",
                      )
                        ? "red"
                        : "green"
                    }
                  >
                    {candidate.normalized_unit || "单位待确认"}
                  </Tag>
                </label>
              );
            })}
            {!run.coordinate_sets.length ? (
              <div className={styles.emptyPanel}>未识别到坐标数据</div>
            ) : null}
          </div>
        </section>

        <section className={styles.candidatePanel}>
          <div className={styles.panelHeader}>
            <Space>
              <FileImageOutlined />
              <Typography.Text strong>位号图页面</Typography.Text>
            </Space>
            <Typography.Text type="secondary">
              从 {roleCount(run, "assembly_drawing")} 个图纸文件中识别
            </Typography.Text>
          </div>
          {run.drawing_pages.length ? (
            <div className={styles.pageGrid}>
              {run.drawing_pages.map((page) => {
                const source = sourceById.get(page.source_asset_id);
                const selected = pages[page.page_id] || "unknown";
                return (
                  <article className={styles.pageCandidate} key={page.page_id}>
                    {page.preview_url ? (
                      <img
                        className={styles.pagePreview}
                        src={page.preview_url}
                        alt={`${source?.relative_path || "位号图"} 第 ${page.page_number} 页`}
                      />
                    ) : (
                      <div className={styles.pagePreview} />
                    )}
                    <div className={styles.pageMeta}>
                      <Typography.Text strong ellipsis={{ tooltip: source?.relative_path }}>
                        {source?.relative_path || "图纸"}
                      </Typography.Text>
                      <Typography.Paragraph
                        type="secondary"
                        ellipsis={{ rows: 1, tooltip: true }}
                        style={{ margin: "2px 0 8px" }}
                      >
                        第 {page.page_number} 页 · 提取 {page.extracted_refs.length} 个位号
                      </Typography.Paragraph>
                      <Segmented
                        block
                        size="small"
                        value={selected}
                        options={[
                          { label: "不用", value: "unknown" },
                          { label: "正面", value: "top" },
                          { label: "背面", value: "bottom" },
                        ]}
                        onChange={(value) => {
                          const side = value as SmtBoardSide;
                          setPages((current) => {
                            const next = { ...current };
                            if (side === "unknown") {
                              delete next[page.page_id];
                            } else {
                              next[page.page_id] = side;
                            }
                            return next;
                          });
                        }}
                      />
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className={styles.emptyPanel}>
              未找到位号图，可继续使用坐标诊断视图
            </div>
          )}
        </section>
      </div>

      <div className={styles.configurationBar}>
        <Space wrap size={16}>
          <label>
            <Typography.Text strong>坐标覆盖范围</Typography.Text>
            <br />
            <Select
              aria-label="坐标覆盖范围"
              value={scope}
              style={{ width: 220, marginTop: 5 }}
              options={SCOPE_OPTIONS.map((item) => ({
                value: item.value,
                label: item.label,
                title: item.description,
              }))}
              onChange={setScope}
            />
          </label>
          {selectedSet?.unit_state === "unknown" ? (
            <label>
              <Typography.Text strong>坐标单位</Typography.Text>
              <br />
              <Select
                aria-label="坐标单位"
                placeholder="请选择"
                value={unit}
                style={{ width: 130, marginTop: 5 }}
                options={[
                  { value: "mm", label: "毫米 mm" },
                  { value: "mil", label: "密尔 mil" },
                  { value: "inch", label: "英寸 inch" },
                ]}
                onChange={setUnit}
              />
            </label>
          ) : null}
          <Typography.Text type="secondary" style={{ maxWidth: 400 }}>
            {SCOPE_OPTIONS.find((item) => item.value === scope)?.description}
          </Typography.Text>
        </Space>
        <Button
          type="primary"
          icon={<CheckCircleOutlined />}
          loading={busy}
          disabled={!canContinue}
          onClick={() => {
            if (!selectedSet) return;
            onConfirm({
              coordinate_set_id: selectedSet.coordinate_set_id,
              scope_semantics: scope,
              pages,
              ...(unit ? { unit } : {}),
              side_mapping: selectedSet.side_mapping,
            });
          }}
        >
          确认识别结果
        </Button>
      </div>
      {duplicateSide ? (
        <Alert
          type="error"
          showIcon
          message="同一面选择了多个位号图页面，请保留一个。"
          style={{ marginTop: 10 }}
        />
      ) : null}
      {error ? (
        <Alert type="error" showIcon message={error} style={{ marginTop: 10 }} />
      ) : null}
    </div>
  );
}
