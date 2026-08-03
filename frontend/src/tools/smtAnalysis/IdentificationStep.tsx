import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
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

import { SmtBoardViewport } from "../../components/SmtBoardViewport";
import type { SourceConfirmationInput } from "./api";
import { ReferenceNavigator } from "./ReferenceNavigator";
import type {
  SmtAnalysisRunResponse,
  SmtBoardSide,
  SmtCoordinateScope,
  SmtPlacement,
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

const NC_STATES = new Set(["confirmed_nc", "candidate_nc"]);

function pageContainsRef(page: SmtAnalysisRunResponse["drawing_pages"][number], ref: string) {
  const normalized = ref.toUpperCase();
  return (
    page.positioned_refs?.some((item) => item.ref.toUpperCase() === normalized) ||
    page.extracted_refs.some((item) => item.toUpperCase() === normalized)
  );
}

function pageForPlacement(
  run: SmtAnalysisRunResponse,
  placement: SmtPlacement,
  currentPageId?: string,
) {
  const matches = run.drawing_pages.filter((page) =>
    pageContainsRef(page, placement.ref),
  );
  return (
    matches.find((page) => page.page_id === currentPageId) ||
    matches.find(
      (page) =>
        page.drawing_role.startsWith("board_") &&
        page.side_candidate === placement.side,
    ) ||
    matches.find((page) => page.drawing_role.startsWith("board_")) ||
    matches.find((page) => page.side_candidate === placement.side) ||
    matches[0]
  );
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
  const firstPlacement = useMemo(
    () =>
      run.placements.find((item) => NC_STATES.has(item.assembly_state)) ||
      run.placements[0],
    [run.placements],
  );
  const [selectedRef, setSelectedRef] = useState(
    firstPlacement?.ref || "",
  );
  const [selectedPageId, setSelectedPageId] = useState(() => {
    const page = firstPlacement
      ? pageForPlacement(run, firstPlacement)
      : undefined;
    return (
      page?.page_id ||
      run.drawing_pages.find((item) => item.side_candidate === "top")
        ?.page_id ||
      run.drawing_pages[0]?.page_id ||
      ""
    );
  });
  const [showBlockingDetails, setShowBlockingDetails] = useState(false);
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
  const previewPages = useMemo(
    () =>
      run.drawing_pages.filter(
        (page) => Boolean(page.preview_url) || page.extracted_refs.length > 0,
      ),
    [run.drawing_pages],
  );
  const selectedPage = useMemo(
    () =>
      run.drawing_pages.find((page) => page.page_id === selectedPageId) ||
      previewPages[0],
    [previewPages, run.drawing_pages, selectedPageId],
  );
  const selectedPageSide = selectedPage
    ? pages[selectedPage.page_id] === "top" || pages[selectedPage.page_id] === "bottom"
      ? pages[selectedPage.page_id]
      : selectedPage.side_candidate === "top" ||
          selectedPage.side_candidate === "bottom"
        ? selectedPage.side_candidate
        : undefined
    : undefined;
  const chosenSides = Object.values(pages);
  const duplicateSide =
    chosenSides.filter((side) => side === "top").length > 1 ||
    chosenSides.filter((side) => side === "bottom").length > 1;
  const canContinue =
    Boolean(selectedSet) &&
    !duplicateSide &&
    (!run.drawing_pages.length || chosenSides.length > 0) &&
    (selectedSet?.unit_state !== "unknown" || Boolean(unit));

  useEffect(() => {
    setSelectedRef(firstPlacement?.ref || "");
    const page = firstPlacement
      ? pageForPlacement(run, firstPlacement)
      : undefined;
    setSelectedPageId(
      page?.page_id ||
        run.drawing_pages.find((item) => item.side_candidate === "top")
          ?.page_id ||
        run.drawing_pages[0]?.page_id ||
        "",
    );
  }, [firstPlacement, run.drawing_pages, run.run_id]);

  function selectPlacement(placement: SmtPlacement) {
    setSelectedRef(placement.ref);
    const page = pageForPlacement(run, placement, selectedPageId);
    if (page) setSelectedPageId(page.page_id);
  }

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
          description={
            <Space direction="vertical" size={4}>
              <Typography.Text>
                检测到 {run.blocking_reasons.length} 项需要确认，先选择位号查看对应位号图。
              </Typography.Text>
              <Button
                type="link"
                size="small"
                style={{ padding: 0, alignSelf: "flex-start" }}
                onClick={() => setShowBlockingDetails((current) => !current)}
              >
                {showBlockingDetails ? "收起详情" : "查看详情"}
              </Button>
              {showBlockingDetails ? (
                <div style={{ maxHeight: 160, overflow: "auto" }}>
                  {run.blocking_reasons.slice(0, 30).map((reason, index) => (
                    <Typography.Paragraph key={`${index}-${reason}`} style={{ margin: "0 0 4px" }}>
                      {reason}
                    </Typography.Paragraph>
                  ))}
                  {run.blocking_reasons.length > 30 ? (
                    <Typography.Text type="secondary">
                      其余 {run.blocking_reasons.length - 30} 项已折叠。
                    </Typography.Text>
                  ) : null}
                </div>
              ) : null}
            </Space>
          }
          style={{ marginBottom: 12 }}
        />
      ) : null}

      <div className={styles.identificationSourceBar}>
        <div className={styles.identificationSourceMain}>
          <Space size={8}>
            <TableOutlined />
            <Typography.Text strong>坐标数据</Typography.Text>
            <Tag>{run.coordinate_sets.length} 个候选</Tag>
          </Space>
          <Select
            aria-label="坐标数据"
            value={coordinateSetId || undefined}
            placeholder="选择坐标文件或工作表"
            style={{ minWidth: 320, maxWidth: "100%" }}
            options={run.coordinate_sets.map((candidate) => {
              const source = sourceById.get(candidate.source_asset_id);
              return {
                value: candidate.coordinate_set_id,
                label: `${source?.relative_path || candidate.sheet_or_section} · ${candidate.quality_report.valid_rows} 个位号`,
              };
            })}
            onChange={setCoordinateSetId}
          />
          {selectedSet ? (
            <Typography.Text type="secondary">
              已识别 {selectedSet.quality_report.valid_rows} 个坐标位号
              {selectedSet.sheet_or_section ? ` · ${selectedSet.sheet_or_section}` : ""}
            </Typography.Text>
          ) : null}
        </div>
        {!run.coordinate_sets.length ? (
          <Typography.Text type="secondary">未识别到坐标数据</Typography.Text>
        ) : null}
      </div>

      <div className={styles.identificationWorkspace}>
        <ReferenceNavigator
          run={run}
          selectedRef={selectedRef}
          onSelect={selectPlacement}
        />
        <section className={styles.identificationPreview}>
          <div className={styles.panelHeader}>
            <Space size={8}>
              <FileImageOutlined />
              <Typography.Text strong>位号图原页</Typography.Text>
            </Space>
            <Typography.Text type="secondary">
              点击左侧位号后自动定位
            </Typography.Text>
          </div>
          <div className={styles.pageSelectionBar}>
            <Typography.Text strong>当前页面</Typography.Text>
            <Select
              aria-label="当前位号图页面"
              value={selectedPage?.page_id || undefined}
              placeholder="选择 PDF 位号图页面"
              style={{ minWidth: 280, maxWidth: "100%" }}
              options={previewPages.map((page) => {
                const source = sourceById.get(page.source_asset_id);
                return {
                  value: page.page_id,
                  label: `${source?.relative_path || "位号图"} · 第 ${page.page_number} 页 · ${page.extracted_refs.length} 个位号`,
                };
              })}
              onChange={setSelectedPageId}
            />
            {selectedPage ? (
              <Segmented
                size="small"
                value={pages[selectedPage.page_id] || "unknown"}
                options={[
                  { label: "不使用", value: "unknown" },
                  { label: "正面", value: "top" },
                  { label: "背面", value: "bottom" },
                ]}
                onChange={(value) => {
                  const nextSide = value as SmtBoardSide;
                  setPages((current) => {
                    const next = { ...current };
                    if (nextSide === "unknown") {
                      delete next[selectedPage.page_id];
                    } else {
                      next[selectedPage.page_id] = nextSide;
                    }
                    return next;
                  });
                }}
              />
            ) : null}
          </div>
          <div className={styles.pageAssignmentList}>
            {previewPages.map((page) => {
              const source = sourceById.get(page.source_asset_id);
              return (
                <div
                  className={styles.pageAssignment}
                  data-testid={`smt-page-assignment-${page.page_id}`}
                  key={page.page_id}
                >
                  <Button
                    type={page.page_id === selectedPage?.page_id ? "link" : "text"}
                    size="small"
                    onClick={() => setSelectedPageId(page.page_id)}
                  >
                    {source?.relative_path || "位号图"} · 第 {page.page_number} 页
                  </Button>
                  <Segmented
                    size="small"
                    value={pages[page.page_id] || "unknown"}
                    options={[
                      { label: "不用", value: "unknown" },
                      { label: "正面", value: "top" },
                      { label: "背面", value: "bottom" },
                    ]}
                    onChange={(value) => {
                      const nextSide = value as SmtBoardSide;
                      setPages((current) => {
                        const next = { ...current };
                        if (nextSide === "unknown") {
                          delete next[page.page_id];
                        } else {
                          next[page.page_id] = nextSide;
                        }
                        return next;
                      });
                    }}
                  />
                </div>
              );
            })}
          </div>
          <div className={styles.identificationPreviewViewport}>
            <SmtBoardViewport
              run={run}
              pageId={selectedPage?.page_id}
              side={selectedPageSide}
              selectedRef={selectedRef}
              onSelect={selectPlacement}
            />
          </div>
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
