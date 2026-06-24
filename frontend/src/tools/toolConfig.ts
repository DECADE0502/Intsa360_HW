export const toolInputs: Record<string, Array<{ key: string; label: string; multiple?: boolean; accept?: string }>> = {
  bom_compare: [
    { key: "bom1", label: "BOM1 文件", accept: ".xlsx,.xls" },
    { key: "bom2", label: "BOM2 文件", accept: ".xlsx,.xls" },
  ],
  bom_risk_check: [{ key: "bom", label: "BOM 文件", accept: ".xlsx,.xls" }],
  netlist_compare: [
    { key: "netlist1", label: "网表1文件夹文件", multiple: true, accept: ".dat" },
    { key: "netlist2", label: "网表2文件夹文件", multiple: true, accept: ".dat" },
  ],
  smt_package_check: [
    { key: "netlist", label: "网表文件夹文件", multiple: true, accept: ".dat" },
    { key: "bom", label: "BOM 文件", accept: ".xlsx,.xls" },
  ],
  single_network_check: [{ key: "netlist", label: "网表文件夹文件", multiple: true, accept: ".dat" }],
};
