import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, App, Button, Descriptions, Drawer, Empty, Segmented, Space, Spin, Tag, Typography, Upload } from "antd";
import { DownloadOutlined, FileExcelOutlined, FolderOpenOutlined, LinkOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { HistoryBomPicker } from "../../components/HistoryBomPicker";
import { uploadFiles, uploadFileTree, type AssetItem } from "../../api/client";
import { toUserMessage } from "../../api/errors";
import { outputHref } from "../../utils/outputHref";
import { useToolWorkspace } from "../../state/toolWorkspace";
import { BoardCanvas } from "./BoardCanvas";
import { createSmtBoard, getSmtBoard } from "./api";
import { RefList } from "./RefList";
import type { BoardSide, SmtBoard, ViewMode } from "./types";
import styles from "./smtView.module.css";

function BomFileButton({ file, onFile }: { file?: File; onFile: (file?: File) => void }) {
  return (
    <Upload accept=".xlsx,.xlsm" maxCount={1} showUploadList={false} beforeUpload={(next) => { onFile(next); return false; }}>
      <Button block icon={<FileExcelOutlined />}>{file ? file.name : "或选择本地 PLM/OA BOM"}</Button>
    </Upload>
  );
}

function statusName(status: string) {
  return ({ placed: "贴装", nc: "NC 未贴" } as Record<string, string>)[status] || status;
}

export function SmtViewPane() {
  const { message } = App.useApp();
  const folderInput = useRef<HTMLInputElement>(null);
  const netlistInput = useRef<HTMLInputElement>(null);
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace("smt_view", { boardId: "" });
  const [folderFiles, setFolderFiles] = useState<File[]>([]);
  const [netlistFiles, setNetlistFiles] = useState<File[]>([]);
  const [historyBom, setHistoryBom] = useState("");
  const [historyAsset, setHistoryAsset] = useState<AssetItem | undefined>();
  const [bomFile, setBomFile] = useState<File>();
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
    netlistInput.current?.setAttribute("webkitdirectory", "");
  }, []);

  useEffect(() => {
    const boardId = String(workspace.boardId || "");
    if (!boardId || board) return;
    setLoading(true);
    getSmtBoard(boardId).then(setBoard).catch(() => resetWorkspace()).finally(() => setLoading(false));
  }, [board, resetWorkspace, workspace.boardId]);

  const selected = useMemo(() => board?.placements.find((item) => item.ref === selectedRef), [board, selectedRef]);
  const modes = useMemo<Array<{ label: string; value: ViewMode }>>(() => {
    const options: Array<{ label: string; value: ViewMode }> = [
      { label: "贴装状态", value: "placement" },
      { label: "NC 专项", value: "nc" },
    ];
    if ((board?.summary.package_checked || 0) > 0) options.push({ label: "封装一致性", value: "package" });
    options.push({ label: "备料风险", value: "supply" });
    return options;
  }, [board]);

  const run = useCallback(async () => {
    if (!folderFiles.length) { message.warning("请先选择完整的 SMT 贴片资料目录。"); return; }
    if (!historyBom && !bomFile) { message.warning("请选择历史成品 BOM 或上传已处理 BOM。"); return; }
    if (netlistFiles.length && !netlistFiles.some((file) => file.name.toLowerCase() === "pstxprt.dat")) {
      message.warning("网表目录中没有找到 pstxprt.dat。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [treeUpload, bomUpload, netlistUpload] = await Promise.all([
        uploadFileTree(folderFiles),
        bomFile ? uploadFiles([bomFile]) : Promise.resolve(null),
        netlistFiles.length ? uploadFileTree(netlistFiles) : Promise.resolve(null),
      ]);
      const next = await createSmtBoard({
        source_dir: treeUpload.folder,
        bom_path: historyBom || bomUpload?.files[0]?.path || "",
        semantic_manifest_path: historyAsset?.semantic_manifest || undefined,
        netlist_dir: netlistUpload?.folder,
        label: treeUpload.root_name || undefined,
      });
      setBoard(next);
      setWorkspace({ boardId: next.board_id });
      setSelectedRef("");
      setSide(next.drawings.top ? "top" : "bottom");
      setMode("placement");
    } catch (reason) {
      setError(toUserMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [bomFile, folderFiles, historyAsset, historyBom, message, netlistFiles, setWorkspace]);

  function clear() {
    setFolderFiles([]);
    setNetlistFiles([]);
    if (folderInput.current) folderInput.current.value = "";
    if (netlistInput.current) netlistInput.current.value = "";
    setHistoryBom("");
    setHistoryAsset(undefined);
    setBomFile(undefined);
    setBoard(null);
    setSelectedRef("");
    setError("");
    resetWorkspace();
  }

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <div>
          <Typography.Title level={3}>贴片视图</Typography.Title>
          <Typography.Text type="secondary">在真实位号图上核对贴装、NC、封装一致性和备料风险。</Typography.Text>
        </div>
        {board ? <Button icon={<ReloadOutlined />} onClick={clear}>更换资料</Button> : null}
      </div>

      {!board ? (
        <section className={styles.sourcePanel}>
          <div className={styles.sourceItem}>
            <strong>1. SMT 贴片资料目录</strong>
            <span>自动识别 XY.txt 与 SMD/REF 位号图，并自动完成双面配准。</span>
            <input
              ref={folderInput}
              type="file"
              multiple
              hidden
              onChange={(event) => setFolderFiles(
                Array.from(event.target.files || []).filter((file) => /\.(txt|pdf)$/i.test(file.name)),
              )}
            />
            <Button icon={<FolderOpenOutlined />} onClick={() => folderInput.current?.click()}>
              {folderFiles.length ? `已识别 ${folderFiles.length} 个 TXT/PDF 候选文件` : "选择整个目录"}
            </Button>
          </div>
          <div className={styles.sourceItem}>
            <strong>2. 已处理成品 BOM</strong>
            <span>成品 BOM 中存在的位号为贴装；XY 有而成品 BOM 没有的位号直接判为 NC。</span>
            <HistoryBomPicker value={historyBom} onChange={(path, asset) => { setHistoryBom(path); setHistoryAsset(asset); if (path) setBomFile(undefined); }} />
            <BomFileButton file={bomFile} onFile={(file) => { setBomFile(file); if (file) { setHistoryBom(""); setHistoryAsset(undefined); } }} />
          </div>
          <div className={styles.sourceItem}>
            <strong>3. Allegro 网表目录（可选）</strong>
            <span>包含 pstxprt.dat 时增加封装一致性视图，并保留可下载的检查报告。</span>
            <input
              ref={netlistInput}
              type="file"
              multiple
              hidden
              onChange={(event) => setNetlistFiles(Array.from(event.target.files || []).filter((file) => file.name.toLowerCase().endsWith(".dat")))}
            />
            <Button icon={<FolderOpenOutlined />} onClick={() => netlistInput.current?.click()}>
              {netlistFiles.length ? `已选择 ${netlistFiles.length} 个 DAT 文件` : "选择网表目录"}
            </Button>
          </div>
          <div className={styles.sourceActions}>
            <Button type="primary" size="large" icon={<PlayCircleOutlined />} loading={loading} onClick={run}>生成贴片视图</Button>
            <Button size="large" onClick={clear}>清空</Button>
          </div>
        </section>
      ) : null}

      {error ? <Alert type="error" showIcon message="生成失败" description={error} /> : null}
      {loading && !board ? <div className={styles.loading}><Spin tip="正在配准位号图并关联成品 BOM" /></div> : null}

      {board ? (
        <>
          {board.notices.map((notice) => <Alert key={notice} type="info" showIcon message={notice} />)}
          <section className={styles.summaryBar}>
            <div><strong>{board.summary.total || 0}</strong><span>XY 位号</span></div>
            <div><strong>{board.summary.placed || 0}</strong><span>贴装</span></div>
            <div><strong>{board.summary.nc || 0}</strong><span>NC</span></div>
            <div><strong>{board.summary.package_issues || 0}</strong><span>封装问题</span></div>
            <button type="button" onClick={() => setUnmappedOpen(true)}><strong>{board.summary.bom_only || 0}</strong><span>BOM 有、坐标无</span></button>
          </section>
          <section className={styles.registrationBar}>
            {(Object.entries(board.drawings) as Array<[BoardSide, NonNullable<SmtBoard["drawings"][BoardSide]>]>).map(([key, drawing]) => (
              <div key={key}>
                <strong>{key === "top" ? "正面" : "背面"}配准</strong>
                <span>{drawing.registration.anchor_count} 个锚点</span>
                <span>中位 {drawing.registration.median_mm.toFixed(3)} mm</span>
                <span>p90 {drawing.registration.p90_mm.toFixed(3)} mm</span>
                <span>最大 {drawing.registration.max_mm.toFixed(3)} mm</span>
                {drawing.registration.rejected_count ? <Tag color="gold">剔除 {drawing.registration.rejected_count}</Tag> : <Tag color="green">无需剔除</Tag>}
              </div>
            ))}
          </section>
          <div className={styles.viewToolbar}>
            <Segmented value={mode} options={modes} onChange={(value) => setMode(value as ViewMode)} />
            <Segmented
              value={side}
              options={(["top", "bottom"] as BoardSide[]).filter((value) => board.drawings[value]).map((value) => ({
                label: `${value === "top" ? "正面" : "背面"} ${board.summary[value] || 0}`,
                value,
              }))}
              onChange={(value) => { setSide(value as BoardSide); setSelectedRef(""); }}
            />
            <Space wrap>
              {board.package_report_outputs.map((path) => <Button key={path} icon={<DownloadOutlined />} href={outputHref(path)}>下载封装报告</Button>)}
              <Button icon={<LinkOutlined />} href={board.reference_drawing_url} target="_blank">打开原始位号图</Button>
            </Space>
          </div>
          <div className={styles.workbench}>
            <RefList placements={board.placements.filter((item) => item.side === side)} selectedRef={selectedRef} onSelect={setSelectedRef} onQueryRefs={setQueryRefs} />
            <BoardCanvas board={board} side={side} mode={mode} selectedRef={selectedRef} highlightedRefs={queryRefs} onSelect={setSelectedRef} />
            <aside className={styles.detailPane}>
              {selected ? (
                <>
                  <div className={styles.detailTitle}><Typography.Title level={4}>{selected.ref}</Typography.Title><Tag color={selected.status === "nc" ? "red" : "green"}>{statusName(selected.status)}</Tag></div>
                  <Descriptions column={1} size="small" bordered>
                    <Descriptions.Item label="物料编码">{selected.material_code || "-"}</Descriptions.Item>
                    <Descriptions.Item label="名称 / 型号">{[selected.name, selected.model].filter(Boolean).join(" / ") || "-"}</Descriptions.Item>
                    <Descriptions.Item label="XY 封装">{selected.footprint || "-"}</Descriptions.Item>
                    <Descriptions.Item label="BOM 封装">{selected.package || "-"}</Descriptions.Item>
                    <Descriptions.Item label="坐标">{selected.x_mm.toFixed(3)}, {selected.y_mm.toFixed(3)} mm</Descriptions.Item>
                    <Descriptions.Item label="判定原因">{selected.reason}</Descriptions.Item>
                    {selected.package_status ? <Descriptions.Item label="封装检查"><Tag color={selected.package_status === "通过" ? "green" : "orange"}>{selected.package_status}</Tag></Descriptions.Item> : null}
                    {selected.net_package ? <Descriptions.Item label="网表封装">{selected.net_package}</Descriptions.Item> : null}
                    {selected.package_note ? <Descriptions.Item label="封装说明">{selected.package_note}</Descriptions.Item> : null}
                  </Descriptions>
                  {selected.description ? <Typography.Paragraph className={styles.description}>{selected.description}</Typography.Paragraph> : null}
                </>
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击左侧位号或图中标记查看详情" />}
            </aside>
          </div>
          <Drawer title="BOM 有、XY 坐标无" width={520} open={unmappedOpen} onClose={() => setUnmappedOpen(false)}>
            {board.bom_only.length ? board.bom_only.map((item) => <div className={styles.unmappedRow} key={item.ref}><strong>{item.ref}</strong><span>{item.material_code || item.reason}</span></div>) : <Empty description="无" />}
          </Drawer>
        </>
      ) : null}
    </div>
  );
}
