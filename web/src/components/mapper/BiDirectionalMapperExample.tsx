/**
 * Example usage of the BiDirectionalMapper with real data
 * This demonstrates how to integrate the 2-node mapper into your application
 */

import React from "react";
import {
  BiDirectionalMapper,
  type System,
  type CatalogField,
} from "./index";
import "./mapper.css";

// Example data structures
const exampleSystems: Record<string, System> = {
  salesforce: {
    id: "salesforce",
    name: "Salesforce",
    kind: "CRM",
  },
  sap: {
    id: "sap",
    name: "SAP ERP",
    kind: "ERP",
  },
};

const exampleFields: Record<string, CatalogField[]> = {
  salesforce: [
    {
      id: "sf-acct-id",
      object_id: "sf-accounts",
      name: "account_id",
      label: "Account ID",
      data_type: "string",
      required: true,
      nullable: false,
      default_value: null,
      position: 0,
    },
    {
      id: "sf-acct-name",
      object_id: "sf-accounts",
      name: "account_name",
      label: "Account Name",
      data_type: "string",
      required: true,
      nullable: false,
      default_value: null,
      position: 1,
    },
    {
      id: "sf-industry",
      object_id: "sf-accounts",
      name: "industry",
      label: "Industry",
      data_type: "string",
      required: false,
      nullable: true,
      default_value: null,
      position: 2,
    },
    {
      id: "sf-annual-revenue",
      object_id: "sf-accounts",
      name: "annual_revenue",
      label: "Annual Revenue",
      data_type: "number",
      required: false,
      nullable: true,
      default_value: null,
      position: 3,
    },
    {
      id: "sf-created-date",
      object_id: "sf-accounts",
      name: "created_date",
      label: "Created Date",
      data_type: "date",
      required: true,
      nullable: false,
      default_value: null,
      position: 4,
    },
    {
      id: "sf-status",
      object_id: "sf-accounts",
      name: "status",
      label: "Status",
      data_type: "string",
      required: true,
      nullable: false,
      default_value: "Active",
      position: 5,
    },
  ],
  sap: [
    {
      id: "sap-cust-num",
      object_id: "sap-customers",
      name: "customer_number",
      label: "Customer Number",
      data_type: "string",
      required: true,
      nullable: false,
      default_value: null,
      position: 0,
    },
    {
      id: "sap-cust-name",
      object_id: "sap-customers",
      name: "customer_name",
      label: "Customer Name",
      data_type: "string",
      required: true,
      nullable: false,
      default_value: null,
      position: 1,
    },
    {
      id: "sap-industry-key",
      object_id: "sap-customers",
      name: "industry_key",
      label: "Industry Key",
      data_type: "string",
      required: false,
      nullable: true,
      default_value: null,
      position: 2,
    },
    {
      id: "sap-annual-sales",
      object_id: "sap-customers",
      name: "annual_sales",
      label: "Annual Sales",
      data_type: "decimal",
      required: false,
      nullable: true,
      default_value: null,
      position: 3,
    },
    {
      id: "sap-created-on",
      object_id: "sap-customers",
      name: "created_on",
      label: "Created On",
      data_type: "date",
      required: true,
      nullable: false,
      default_value: null,
      position: 4,
    },
    {
      id: "sap-status-code",
      object_id: "sap-customers",
      name: "status_code",
      label: "Status Code",
      data_type: "string",
      required: true,
      nullable: false,
      default_value: "01",
      position: 5,
    },
  ],
};

export default function BiDirectionalMapperExample() {
  const [edges, setEdges] = React.useState<any[]>([
    {
      id: "edge-1",
      source: "system-salesforce",
      target: "system-sap",
      sourceHandle: "output",
      targetHandle: "return-input",
      data: { direction: "outbound" },
    },
    {
      id: "edge-2",
      source: "system-sap",
      target: "system-salesforce",
      sourceHandle: "response-output",
      targetHandle: "request-input",
      data: { direction: "inbound" },
    },
  ]);

  const handleEdgesChange = React.useCallback((newEdges: any[]) => {
    console.log("Edges updated:", newEdges);
    setEdges(newEdges);
    // Here you would typically save the edges to your backend
    // await saveIntegrationEdges(integrationId, newEdges);
  }, []);

  const handleNodesChange = React.useCallback((nodes: any[]) => {
    console.log("Nodes changed:", nodes);
    // Update node positions or other node data
  }, []);

  return (
    <div style={{ width: "100%", height: "100vh", display: "flex", flexDirection: "column" }}>
      <header
        style={{
          padding: "16px 24px",
          borderBottom: "1px solid #e5e7eb",
          background: "#ffffff",
        }}
      >
        <h1 style={{ margin: 0, fontSize: "24px", fontWeight: "600" }}>
          Salesforce → SAP Contract Mapper
        </h1>
        <p style={{ margin: "4px 0 0 0", fontSize: "14px", color: "#6b7280" }}>
          Map fields between Salesforce accounts and SAP customers with bi-directional routing
        </p>
      </header>

      <div style={{ flex: 1, position: "relative" }}>
        <BiDirectionalMapper
          sourceSystem={exampleSystems.salesforce}
          targetSystem={exampleSystems.sap}
          sourceFields={exampleFields.salesforce}
          targetFields={exampleFields.sap}
          initialEdges={edges}
          onEdgesChange={handleEdgesChange}
          onNodesChange={handleNodesChange}
        />
      </div>

      <footer
        style={{
          padding: "12px 24px",
          borderTop: "1px solid #e5e7eb",
          background: "#f9fafb",
          fontSize: "12px",
          color: "#6b7280",
        }}
      >
        <p style={{ margin: 0 }}>
          <strong>Legend:</strong> Blue edges (→) represent outbound data flow from Salesforce to
          SAP. Green edges (←) represent inbound response flow from SAP back to Salesforce.
        </p>
      </footer>
    </div>
  );
}
