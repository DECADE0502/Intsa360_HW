import { App as AntdApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { render } from "@testing-library/react";
import type { PropsWithChildren, ReactElement } from "react";

function TestProviders({ children }: PropsWithChildren) {
  return (
    <ConfigProvider locale={zhCN}>
      <AntdApp>{children}</AntdApp>
    </ConfigProvider>
  );
}

export function renderWithProviders(ui: ReactElement) {
  return render(ui, { wrapper: TestProviders });
}
