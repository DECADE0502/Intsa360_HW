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
  ExperimentOutlined,
  FormOutlined,
} from "@ant-design/icons";

import { SmtBoardViewport } from "../../components/SmtBoardViewport";
import type { RegistrationInput } from "./api";
import { AnchorEditor } from "./AnchorEditor";
import type {
  SmtAnalysisRunResponse,
  SmtRegistrationAnchor,
} from "./types";
import styles from "./SmtAnalysisPane.module.css";


type RegistrationStepProps = {
  run: SmtAnalysisRunResponse;
  busy: boolean;
  error: string;
  onRegister: (input: RegistrationInput) => Promise<void>;
};

function selectedCoordinateSet(run: SmtAnalysisRunResponse) {
  return (
    run.coordinate_sets.find((item) => item.scope_semantics !== "unknown") ||
    run.coordinate_sets[0]
  );
}

export function RegistrationStep({
  run,
  busy,
  error,
  onRegister,
}: RegistrationStepProps) {
  const coordinateSet = selectedCoordinateSet(run);
  const selectedPages = useMemo(
    () =>
      run.drawing_pages.filter(
        (page) =>
          page.side_candidate === "top" || page.side_candidate === "bottom",
      ),
    [run.drawing_pages],
  );
  const [side, setSide] = useState<"top" | "bottom">(
    (selectedPages.find((page) => page.side_candidate === "top")
      ?.side_candidate as "top") ||
      (selectedPages[0]?.side_candidate as "top" | "bottom") ||
      "top",
  );
  const [mode, setMode] = useState<"anchors" | "overlay">("anchors");
  const [model, setModel] =
    useState<RegistrationInput["model"]>("similarity");
  const [anchorsBySide, setAnchorsBySide] = useState<
    Record<string, SmtRegistrationAnchor[]>
  >({});
  const page = selectedPages.find((item) => item.side_candidate === side);
  const registration = run.registrations.find(
    (item) => item.side === side && item.page_id === page?.page_id,
  );
  const anchors = anchorsBySide[side] || registration?.anchors || [];
  const occurrences = (coordinateSet?.occurrences || []).filter(
    (item) => item.side === side || item.side === "unknown",
  );
  const verifiedSides = new Set(
    run.registrations
      .filter((item) => item.confidence_state === "verified")
      .map((item) => item.side),
  );
  const allVerified = selectedPages.every((item) =>
    verifiedSides.has(item.side_candidate as "top" | "bottom"),
  );

  useEffect(() => {
    if (registration) setMode("overlay");
  }, [registration?.registration_id, registration?.confidence_state]);

  if (!coordinateSet) {
    return (
      <Alert
        type="error"
        showIcon
        message="没有可用于校准的坐标数据。"
      />
    );
  }

  if (!selectedPages.length) {
    return (
      <Alert
        type="info"
        showIcon
        message="本次没有位号图，已进入坐标诊断模式。"
        description="可以继续复核 BOM、坐标和 NC 语义，但不会显示真实板面叠加。"
      />
    );
  }

  return (
    <div>
      <div className={styles.configurationBar} style={{ marginTop: 0 }}>
        <Space wrap>
          <Segmented
            value={side}
            options={selectedPages.map((item) => ({
              label: item.side_candidate === "bottom" ? "背面" : "正面",
              value: item.side_candidate,
            }))}
            onChange={(value) => {
              setSide(value as "top" | "bottom");
              setMode("anchors");
            }}
          />
          <Segmented
            value={mode}
            options={[
              {
                label: (
                  <Space size={4}>
                    <FormOutlined />
                    锚点校准
                  </Space>
                ),
                value: "anchors",
              },
              {
                label: (
                  <Space size={4}>
                    <ExperimentOutlined />
                    叠加预览
                  </Space>
                ),
                value: "overlay",
                disabled: !registration,
              },
            ]}
            onChange={(value) => setMode(value as "anchors" | "overlay")}
          />
          <Select
            aria-label="配准模型"
            value={model}
            style={{ width: 180 }}
            options={[
              { value: "similarity", label: "平移 / 旋转 / 等比缩放" },
              { value: "similarity_with_mirror", label: "镜像等比变换" },
              { value: "affine", label: "仿射变换" },
            ]}
            onChange={setModel}
          />
        </Space>
        <Space>
          {registration?.decision_source === "automatic" ? (
            <Tag color="blue">矢量位号自动候选</Tag>
          ) : null}
          {registration ? (
            <Tag
              color={
                registration.confidence_state === "verified"
                  ? "green"
                  : registration.confidence_state === "rejected"
                    ? "red"
                    : "gold"
              }
            >
              {registration.confidence_state === "verified"
                ? "已确认"
                : registration.confidence_state === "rejected"
                  ? "配准无效"
                  : "等待叠加确认"}
            </Tag>
          ) : null}
          {allVerified ? (
            <Tag icon={<CheckCircleOutlined />} color="green">
              正反面均已确认
            </Tag>
          ) : null}
        </Space>
      </div>

      {mode === "anchors" && page ? (
        <div className={styles.registrationLayout}>
          <AnchorEditor
            page={page}
            occurrences={occurrences}
            anchors={anchors}
            onChange={(next) =>
              setAnchorsBySide((current) => ({ ...current, [side]: next }))
            }
          />
        </div>
      ) : (
        <div style={{ height: "min(68vh, 720px)" }}>
          <SmtBoardViewport
            run={run}
            side={side}
            onSideChange={setSide}
          />
        </div>
      )}

      {registration ? (
        <div className={styles.summaryStrip} style={{ marginTop: 12 }}>
          {[
            ["锚点", registration.validation.anchor_count],
            [
              "中位误差",
              registration.validation.median_error == null
                ? "-"
                : registration.validation.median_error.toFixed(2),
            ],
            [
              "P95 误差",
              registration.validation.p95_error == null
                ? "-"
                : registration.validation.p95_error.toFixed(2),
            ],
            [
              "落图比例",
              registration.validation.inside_ratio == null
                ? "-"
                : `${(registration.validation.inside_ratio * 100).toFixed(1)}%`,
            ],
            [
              "空间覆盖",
              registration.validation.spatial_coverage == null
                ? "-"
                : `${(registration.validation.spatial_coverage * 100).toFixed(1)}%`,
            ],
          ].map(([label, value]) => (
            <div className={styles.summaryItem} key={String(label)}>
              <span className={styles.summaryValue}>{value}</span>
              <Typography.Text type="secondary">{label}</Typography.Text>
            </div>
          ))}
        </div>
      ) : null}

      <div className={styles.sourceActions}>
        {mode === "anchors" ? (
          <Button
            type="primary"
            loading={busy}
            disabled={!page || anchors.length < 3}
            onClick={async () => {
              if (!page) return;
              await onRegister({
                coordinate_set_id: coordinateSet.coordinate_set_id,
                page_id: page.page_id,
                side,
                model,
                anchors,
                confirmed: false,
              });
            }}
          >
            计算叠加预览
          </Button>
        ) : (
          <>
            <Button onClick={() => setMode("anchors")}>调整锚点</Button>
            <Button
              type="primary"
              icon={<CheckCircleOutlined />}
              loading={busy}
              disabled={!registration || anchors.length < 3}
              onClick={async () => {
                if (!page) return;
                await onRegister({
                  coordinate_set_id: coordinateSet.coordinate_set_id,
                  page_id: page.page_id,
                  side,
                  model: registration?.model || model,
                  anchors,
                  confirmed: true,
                });
              }}
            >
              确认此面叠加正确
            </Button>
          </>
        )}
      </div>
      {error ? (
        <Alert type="error" showIcon message={error} style={{ marginTop: 10 }} />
      ) : null}
    </div>
  );
}
