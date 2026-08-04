import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, App, Button, Descriptions, Drawer, Empty, Segmented, Space, Spin, Tag, Typography, Upload } from "antd";
import { FileExcelOutlined, FolderOpenOutlined, LinkOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { HistoryBomPicker } from "../../components/HistoryBomPicker";
import { uploadFiles, uploadFileTree, type AssetItem } from "../../api/client";
import { toUserMessage } from "../../api/errors";
import { useToolWorkspace } from "../../state/toolWorkspace";
import { BoardCanvas } from "./BoardCanvas";
import { createSmtBoard, getSmtBoard } from "./api";
import { RefList } from "./RefList";
import type { BoardSide, Placement, SmtBoard, ViewMode } from "./types";
import styles from "./smtView.module.css";

function FileButton({ label, file, onFile }: { label: string; file?: File; onFile: (file?: File) => void }) {
  return (
    <Upload accept=".xlsx,.xlsm,.json" maxCount={1} showUploadList={false} beforeUpload={(next) => { onFile(next); return false; }}>
      <Button block icon={<FileExcelOutlined />}>{file ? file.name : label}</Button>
    </Upload>
  );
}

function statusName(status: string) {
  return ({ placed: "贴装", nc: "NC 未贴", non_smt: "非贴片工艺项", xy_only: "仅坐标存在" } as Record<string, string>)[status] || status;
}

export function SmtViewPane() {
  const { message } = App.useApp();
  const folderInput = useRef<HTMLInputElement>(null);
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace("smt_view", { boardId: "" });
  const [folderFiles, setFolderFiles] = useState<File[]>([]);
  const [historyBom, setHistoryBom] = useState("");
  const [historyAsset, setHistoryAsset] = useState<AssetItem | undefined>();
  const [bomFile, setBomFile] = useState<File>();
  const [ncFile, setNcFile] = useState<File>();
  const [baselineFile, setBaselineFile] = useState<File>();
  const [board, setBoard] = useState<SmtBoard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [side, setSide] = useState<BoardSide>("top");
  const [mode, setMode] = useState<ViewMode>("placement");
  const [selectedRef, setSelectedRef] = useState("");
  const [queryRefs, setQueryRefs] = useState<string[]>([]);
  const [unmappedOpen, setUnmappedOpen] = useState(false);

  useEffect(() => {
    folderInput.current?.setAttribute("webkitdirectory", "");
  }, []);

  useEffect(() => {
    const boardId = String(workspace.boardId || "");
    if (!boardId || board) return;
    setLoading(true);
    getSmtBoard(boardId).then(setBoard).catch(() => resetWorkspace()).finally(() => setLoading(false));
  }, [board, resetWorkspace, workspace.boardId]);

  const selected = useMemo(() => board?.placements.find((item) => item.ref === selectedRef), [board, selectedRef]);
  const modes = useMemo(() => {
    const options = [
      { label: "贴装状态", value: "placement" },
      { label: "NC 专项", value: "nc" },
      { label: "备料风险", value: "supply" },
    ];
    if ((board?.summary.version_changes || 0) > 0) options.push({ label: "版本差异", value: "version" });
    return options;
  }, [board]);

  const run = useCallback(async () => {
    if (!folderFiles.length) { message.warning("请先选择完整的 SMT 贴片资料目录。"); return; }
    if (!historyBom && !bomFile) { message.warning("请选择历史成品 BOM 或上传已处理 BOM。"); return; }
    setLoading(true);
    setError("");
    try {
      const [treeUpload, bomUpload, ncUpload, baselineUpload] = await Promise.all([
        uploadFileTree(folderFiles),
        bomFile ? uploadFiles([bomFile]) : Promise.resolve(null),
        ncFile ? uploadFiles([ncFile]) : Promise.resolve(null),
        baselineFile ? uploadFiles([baselineFile]) : Promise.resolve(null),
      ]);
      const next = await createSmtBoard({
        source_dir: treeUpload.folder,
        bom_path: historyBom || bomUpload?.files[0]?.path || "",
        semantic_manifest_path: historyAsset?.semantic_manifest || undefined,
        decision_manifest_path: historyAsset?.decision_manifest || undefined,
        nc_path: ncUpload?.files[0]?.path,
        baseline_bom_path: baselineUpload?.files[0]?.path,
        label: treeUpload.root_name || undefined,
      });
      setBoard(next);
      setWorkspace({ boardId: next.board_id });
      setSelectedRef("");
      setSide("top");
      setMode("placement");
    } catch (reason) {
      setError(toUserMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [baselineFile, bomFile, folderFiles, historyAsset, historyBom, message, ncFile, setWorkspace]);

  function clear() {
    setFolderFiles([]);
    setHistoryBom("");
    setHistoryAsset(undefined);
    setBomFile(undefined);
    setNcFile(undefined);
    setBaselineFile(undefined);
    setBoard(null);
    setSelectedRef("");
    setError("");
    resetWorkspace();
  }

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <div>
          <Typography.Title level={3}>贴片位号视图</Typography.Title>
          <Typography.Text type="secondary">用 XY 坐标叠加 BOM 判定结果，快速定位贴装、NC 和资料异常位号。</Typography.Text>
        </div>
        {board ? <Button icon={<ReloadOutlined />} onClick={clear}>更换资料</Button> : null}
      </div>

      {!board ? (
        <section className={styles.sourcePanel}>
          <div className={styles.sourceItem}>
            <strong>1. SMT 贴片资料目录</strong>
            <span>自动识别 XY.txt；原始 SMD/REF PDF 仅供打开查看。</span>
            <input
              ref={folderInput}
              type="file"
              multiple
              hidden
              onChange={(event) => setFolderFiles(Array.from(event.target.files || []))}
            />
            <Button icon={<FolderOpenOutlined />} onClick={() => folderInput.current?.click()}>
              {folderFiles.length ? `已选择 ${folderFiles.length} 个文件` : "选择整个目录"}
            </Button>
          </div>
          <div className={styles.sourceItem}>
            <strong>2. 已处理成品 BOM</strong>
            <span>优先使用历史记录，可自动带出完整的 NC 与非贴片判定。</span>
            <HistoryBomPicker value={historyBom} onChange={(path, asset) => { setHistoryBom(path); setHistoryAsset(asset); if (path) setBomFile(undefined); }} />
            <FileButton label="或选择本地 PLM/OA BOM" file={bomFile} onFile={(file) => { setBomFile(file); if (file) { setHistoryBom(""); setHistoryAsset(undefined); } }} />
          </div>
          <div className={styles.sourceItem}>
            <strong>3. 补充资料（可选）</strong>
            <span>本地 BOM 建议同时选择 NC 汇总；旧版 BOM 用于显示换料差异。</span>
            <FileButton label="选择 NC 汇总" file={ncFile} onFile={setNcFile} />
            <FileButton label="选择旧版 BOM" file={baselineFile} onFile={setBaselineFile} />
          </div>
          <div className={styles.sourceActions}>
            <Button type="primary" size="large" icon={<PlayCircleOutlined />} loading={loading} onClick={run}>生成贴片位号视图</Button>
            <Button size="large" onClick={clear}>清空</Button>
          </div>
        </section>
      ) : null}

      {error ? <Alert type="error" showIcon message="生成失败" description={error} /> : null}
      {loading && !board ? <div className={styles.loading}><Spin tip="正在识别资料并关联位号" /></div> : null}

      {board ? (
        <>
          {board.notices.map((notice) => <Alert key={notice} type="warning" showIcon message={notice} />)}
          <section className={styles.summaryBar}>
            <div><strong>{board.summary.total || 0}</strong><span>坐标位号</span></div>
            <div><strong>{board.summary.placed || 0}</strong><span>贴装</span></div>
            <div><strong>{board.summary.nc || 0}</strong><span>NC</span></div>
            <div><strong>{board.summary.non_smt || 0}</strong><span>非贴片</span></div>
            <button type="button" onClick={() => setUnmappedOpen(true)}><strong>{(board.summary.bom_only || 0) + (board.summary.xy_only || 0)}</strong><span>资料差异</span></button>
          </section>
          <div className={styles.viewToolbar}>
            <Segmented value={mode} options={modes} onChange={(value) => setMode(value as ViewMode)} />
            <Segmented value={side} options={[{ label: `正面 ${board.summary.top || 0}`, value: "top" }, { label: `背面 ${board.summary.bottom || 0}`, value: "bottom" }]} onChange={(value) => setSide(value as BoardSide)} />
            {board.reference_drawing_url ? (
              <Button icon={<LinkOutlined />} href={board.reference_drawing_url} target="_blank">打开原始位号图</Button>
            ) : null}
          </div>
          <div className={styles.workbench}>
            <RefList placements={board.placements.filter((item) => item.side === side)} selectedRef={selectedRef} onSelect={setSelectedRef} onQueryRefs={setQueryRefs} />
            <BoardCanvas board={board} side={side} mode={mode} selectedRef={selectedRef} highlightedRefs={queryRefs} onSelect={setSelectedRef} />
            <aside className={styles.detailPane}>
              {selected ? (
                <>
                  <div className={styles.detailTitle}><Typography.Title level={4}>{selected.ref}</Typography.Title><Tag>{statusName(selected.status)}</Tag></div>
                  <Descriptions column={1} size="small" bordered>
                    <Descriptions.Item label="物料编码">{selected.material_code || "-"}</Descriptions.Item>
                    <Descriptions.Item label="名称 / 型号">{[selected.name, selected.model].filter(Boolean).join(" / ") || "-"}</Descriptions.Item>
                    <Descriptions.Item label="封装">{selected.package || selected.footprint || "-"}</Descriptions.Item>
                    <Descriptions.Item label="坐标">{selected.x_mm.toFixed(3)}, {selected.y_mm.toFixed(3)} mm</Descriptions.Item>
                    <Descriptions.Item label="旋转">{selected.rotation}°</Descriptions.Item>
                    <Descriptions.Item label="判定原因">{selected.reason || selected.decision_kind || "成品 BOM 中存在"}</Descriptions.Item>
                    {selected.version_change !== "none" ? <Descriptions.Item label="版本差异">{selected.baseline_material_code || "无"} → {selected.material_code || "无"}</Descriptions.Item> : null}
                  </Descriptions>
                  {selected.description ? <Typography.Paragraph className={styles.description}>{selected.description}</Typography.Paragraph> : null}
                </>
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击左侧位号或板面器件查看详情" />}
            </aside>
          </div>
          <Drawer title="资料差异位号" width={520} open={unmappedOpen} onClose={() => setUnmappedOpen(false)}>
            <Typography.Title level={5}>BOM 有、坐标无（{board.bom_only.length}）</Typography.Title>
            {board.bom_only.length ? board.bom_only.map((item) => <div className={styles.unmappedRow} key={`${item.ref}-${item.version_change}`}><strong>{item.ref}</strong><span>{item.material_code || item.reason}</span></div>) : <Empty description="无" />}
            <Typography.Title level={5}>坐标有、BOM 无（{board.xy_only.length}）</Typography.Title>
            {board.xy_only.length ? <Space wrap>{board.xy_only.map((ref) => <Tag key={ref}>{ref}</Tag>)}</Space> : <Empty description="无" />}
          </Drawer>
        </>
      ) : null}
    </div>
  );
}
