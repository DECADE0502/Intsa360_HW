import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Segmented, Space, Typography, Upload } from "antd";
import { DeleteOutlined, FileTextOutlined } from "@ant-design/icons";

import { uploadFiles } from "../../api/client";
import { toUserMessage } from "../../api/errors";
import { useToolWorkspace } from "../../state/toolWorkspace";
import { fetchRefdesDrawing, openRefdesDrawing } from "./api";
import { RefdesList } from "./RefdesList";
import { RefdesPageView } from "./RefdesPageView";
import { groupMarks, SIDE_LABELS, type RefdesDrawing, type RefdesMark } from "./types";
import styles from "./RefdesViewer.module.css";


type Workspace = { drawingId: string };

const EMPTY_WORKSPACE: Workspace = { drawingId: "" };

export function RefdesViewerPane() {
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace<Workspace>(
    "refdes_viewer",
    EMPTY_WORKSPACE,
  );
  const [drawing, setDrawing] = useState<RefdesDrawing | null>(null);
  const [pageNumber, setPageNumber] = useState(0);
  const [selectedRef, setSelectedRef] = useState("");
  const [markIndex, setMarkIndex] = useState(0);
  const [target, setTarget] = useState<RefdesMark | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function accept(next: RefdesDrawing) {
    setDrawing(next);
    const first = next.pages.find((page) => page.marks.length) || next.pages[0];
    setPageNumber(first?.page_number || 0);
    setSelectedRef("");
    setMarkIndex(0);
    setTarget(null);
    setWorkspace({ drawingId: next.drawing_id });
  }

  // Restore the last drawing so a reload does not lose the work.
  useEffect(() => {
    if (!workspace.drawingId || drawing) return;
    let cancelled = false;
    fetchRefdesDrawing(workspace.drawingId)
      .then((restored) => {
        if (!cancelled) accept(restored);
      })
      .catch(() => {
        if (!cancelled) resetWorkspace();
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace.drawingId]);

  const page = useMemo(
    () =>
      drawing?.pages.find((item) => item.page_number === pageNumber) ||
      drawing?.pages[0],
    [drawing, pageNumber],
  );
  const entries = useMemo(() => (page ? groupMarks(page.marks) : []), [page]);

  async function handleFile(file: File) {
    setBusy(true);
    setError("");
    try {
      const uploaded = await uploadFiles([file]);
      const path = uploaded.files[0]?.path;
      if (!path) throw new Error("上传失败");
      accept(await openRefdesDrawing(path, file.name));
    } catch (uploadError) {
      setError(toUserMessage(uploadError));
    } finally {
      setBusy(false);
    }
  }

  /** Locate a refdes; picking the same row again advances to its next instance. */
  function locate(ref: string) {
    const entry = entries.find((item) => item.ref === ref);
    if (!entry) return;
    const next = ref === selectedRef ? (markIndex + 1) % entry.marks.length : 0;
    setSelectedRef(ref);
    setMarkIndex(next);
    // A fresh object identity re-triggers the jump even for the same mark.
    setTarget({ ...entry.marks[next] });
  }

  function pickMark(mark: RefdesMark) {
    const entry = entries.find((item) => item.ref === mark.ref);
    const index = entry
      ? entry.marks.findIndex((item) => item.order === mark.order)
      : -1;
    setSelectedRef(mark.ref);
    setMarkIndex(index < 0 ? 0 : index);
    setTarget({ ...mark });
  }

  function clear() {
    setDrawing(null);
    setPageNumber(0);
    setSelectedRef("");
    setTarget(null);
    setError("");
    resetWorkspace();
  }

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <div>
          <Typography.Title level={4} className={styles.title}>
            位号图查看
          </Typography.Title>
          <Typography.Text type="secondary">
            只需一份位号图 PDF：左侧列出图上全部位号，点击即在右侧原图定位。
          </Typography.Text>
        </div>
        <Space>
          <Upload
            accept=".pdf,.png,.jpg,.jpeg"
            showUploadList={false}
            beforeUpload={(file) => {
              void handleFile(file);
              return false;
            }}
          >
            <Button type="primary" loading={busy} icon={<FileTextOutlined />}>
              选择位号图
            </Button>
          </Upload>
          {drawing ? (
            <Button icon={<DeleteOutlined />} onClick={clear}>
              清空
            </Button>
          ) : null}
        </Space>
      </div>

      {error ? <Alert type="error" showIcon message={error} className={styles.notice} /> : null}

      {drawing ? (
        <>
          <div className={styles.docBar}>
            <Space size={12} wrap>
              <Typography.Text strong>{drawing.file_name}</Typography.Text>
              <Typography.Text type="secondary">
                {drawing.page_count} 页 · {drawing.ref_count} 个位号
              </Typography.Text>
              {drawing.pages.length > 1 ? (
                <Segmented
                  size="small"
                  value={page?.page_number}
                  onChange={(value) => {
                    setPageNumber(Number(value));
                    setSelectedRef("");
                    setTarget(null);
                  }}
                  options={drawing.pages.map((item) => ({
                    label:
                      item.side_guess === "unknown"
                        ? `第 ${item.page_number} 页 · ${item.ref_count}`
                        : `${SIDE_LABELS[item.side_guess]} · ${item.ref_count}`,
                    value: item.page_number,
                  }))}
                />
              ) : null}
            </Space>
          </div>

          {drawing.notices.map((notice) => (
            <Alert
              key={notice}
              type="warning"
              showIcon
              message={notice}
              className={styles.notice}
            />
          ))}

          {page ? (
            <div className={styles.workspace}>
              <RefdesList
                entries={entries}
                selectedRef={selectedRef}
                markIndex={markIndex}
                onSelect={locate}
              />
              <RefdesPageView
                key={page.page_number}
                page={page}
                selectedRef={selectedRef}
                target={target}
                onPick={pickMark}
              />
            </div>
          ) : null}
        </>
      ) : (
        <div className={styles.placeholder}>
          <Typography.Text type="secondary">
            选择一份位号图 PDF 即可开始，不需要 BOM、坐标文件或配准。
          </Typography.Text>
        </div>
      )}
    </div>
  );
}
