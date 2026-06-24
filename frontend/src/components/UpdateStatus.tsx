import { useEffect, useState } from "react";
import { Button, message, Space, Tag } from "antd";
import { fetchVersion, startUpdate } from "../api/client";

export function UpdateStatus() {
  const [version, setVersion] = useState("");

  useEffect(() => {
    fetchVersion().then(setVersion).catch(() => setVersion("未知"));
  }, []);

  return (
    <Space>
      <Tag>版本 {version || "加载中"}</Tag>
      <Button
        size="small"
        onClick={async () => {
          await startUpdate();
          message.success("已开始更新，稍后会自动重启服务");
        }}
      >
        一键更新
      </Button>
    </Space>
  );
}
