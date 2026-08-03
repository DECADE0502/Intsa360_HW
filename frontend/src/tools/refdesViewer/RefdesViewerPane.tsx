import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Segmented, Space, Typography, Upload } from "antd";
import { DeleteOutlined, FileTextOutlined } from "@ant-design/icons";

import { uploadFiles } from "../../api/client";
import { toUserMessage } from "../../api/errors";
import { useToolWorkspace } from "../../state/toolWorkspace";
import { fetchRefdesDocument, openRefdesDocument } from "./api";
import { RefdesCanvas } from "./RefdesCanvas";
import { RefdesList } from "./RefdesList";
import { SIDE_LABELS, type RefdesDocument, type RefdesEntry, type RefdesOccurrence } from "./types";
import styles from "./RefdesViewer.module.css";


type Workspace = {
  docId: string;
  fileName: string;
};

const EMPTY_WORKSPACE: Workspace = { docId: "", fileName: "" };

function naturalCompare(left: string, right: string) {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

/** Group a page's occurrences by refdes so each designator is one list row. */
function buildEntries(occurrences: RefdesOccurrence[]): RefdesEntry[] {
  const grouped = new Map<string, RefdesOccurrence[]>();
  occurrences.forEach((item) => {
    const bucket = grouped.get(item.ref);
    if (bucket) bucket.push(item);
    else grouped.set(item.ref, [item]);
  });
  return Array.from(grouped.entries())
    .map(([ref, items]) => ({ ref, occurrences: items }))
    .sort((left, right) => naturalCompare(left.ref, right.ref));
}

export function RefdesViewerPane() {
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace<Workspace>(
    "refdes_viewer",
    EMPTY_WORKSPACE,
  );
  const [document, setDocument] = useState<RefdesDocument | null>(null);
  const [pageId, setPageId] = useState("");
  const [selectedRef, setSelectedRef] = useState("");
  const [occurrenceIndex, setOccurrenceIndex] = useState(0);
  const [target, setTarget] = useState<RefdesOccurrence | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function acceptDocument(next: RefdesDocument) {
    setDocument(next);
    const first =
      next.pages.find((page) => page.occurrence_count) || next.pages[0];
    setPageId(first?.page_id || "");
    setSelectedRef("");
    setOccurrenceIndex(0);
    setTarget(null);
    setWorkspace({ docId: next.doc_id, fileName: next.file_name });
  }

  // Restore the last opened drawing so a page refresh does not lose the work.
  useEffect(() => {
    if (!workspace.docId || document) return;
    let cancelled = false;
    fetchRefdesDocument(workspace.docId)
      .then((restored) => {
        if (!cancelled) acceptDocument(restored);
      })
      .catch(() => {
        if (!cancelled) resetWorkspace();
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace.docId]);

  const page = useMemo(
    () =>
      document?.pages.find((item) => item.page_id === pageId) ||
      document?.pages[0],
    [document, pageId],
  );
  const entries = useMemo(
    () => (page ? buildEntries(page.occurrences) : []),
    [page],
  );

  async function handleUpload(file: File) {
    setBusy(true);
    setError("");
    try {
      const uploaded = await uploadFiles([file]);
      const path = uploaded.files[0]?.path;
      if (!path) throw new Error("上传失败");
      acceptDocument(await openRefdesDocument(path, file.name));
    } catch (uploadError) {
      setError(toUserMessage(uploadError));
    } finally {
      setBusy(false);
    }
  }

  /** Locate a refdes: same row again advances to its next printed instance. */
  function locate(ref: string) {
    const entry = entries.find((item) => item.ref === ref);
    if (!entry) return;
    const next =
      ref === selectedRef
        ? (occurrenceIndex + 1) % entry.occurrences.length
        : 0;
    setSelectedRef(ref);
    setOccurrenceIndex(next);
    // A fresh object identity re-triggers the canvas locate effect even when the
    // same occurrence is requested twice.
    setTarget({ ...entry.occurrences[next] });
  }

  function locateOccurrence(occurrence: RefdesOccurrence) {
    const entry = entries.find((item) => item.ref === occurrence.ref);
    const index = entry
      ? entry.occurrences.findIndex(
          (item) => item.occurrence_id === occurrence.occurrence_id,
        )
      : -1;
    setSelectedRef(occurrence.ref);
    setOccurrenceIndex(index < 0 ? 0 : index);
    setTarget({ ...occurrence });
  }

  function clear() {
    setDocument(null);
    setPageId("");
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
              void handleUpload(file);
              return false;
            }}
          >
            <Button type="primary" loading={busy} icon={<FileTextOutlined />}>
              选择位号图
            </Button>
          </Upload>
          {document ? (
            <Button icon={<DeleteOutlined />} onClick={clear}>
              清空
            </Button>
          ) : null}
        </Space>
      </div>

      {error ? (
        <Alert type="error" showIcon message={error} className={styles.notice} />
      ) : null}

      {document ? (
        <>
          <div className={styles.docBar}>
            <Space size={12} wrap>
              <Typography.Text strong>{document.file_name}</Typography.Text>
              <Typography.Text type="secondary">
                {document.page_count} 页 · {document.ref_count} 个位号
              </Typography.Text>
              {document.pages.length > 1 ? (
                <Segmented
                  size="small"
                  value={page?.page_id}
                  onChange={(value) => {
                    setPageId(String(value));
                    setSelectedRef("");
                    setTarget(null);
                  }}
                  options={document.pages.map((item) => ({
                    label: `${SIDE_LABELS[item.side_guess]} · ${item.ref_count}`,
                    value: item.page_id,
                  }))}
                />
              ) : null}
            </Space>
          </div>

          {document.notices.map((notice) => (
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
                occurrenceIndex={occurrenceIndex}
                onSelect={locate}
              />
              <RefdesCanvas
                key={page.page_id}
                page={page}
                selectedRef={selectedRef}
                target={target}
                onSelect={locateOccurrence}
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
