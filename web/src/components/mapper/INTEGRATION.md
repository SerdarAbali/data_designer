# Integration Guide: Adding BiDirectionalMapper to IntegrationWorkspace

This guide shows how to integrate the new `BiDirectionalMapper` component into your existing `IntegrationWorkspace`.

## Overview

The `BiDirectionalMapper` is a specialized component for handling 2-node mappings with intelligent routing. It's ideal for scenarios where you want to:

- Visualize bidirectional data flow between two systems
- Automatically route outbound and inbound edges separately
- Apply distinct styling and animations based on direction
- Manage complex field mappings with visual clarity

## Integration Steps

### 1. Import the Mapper Component

```typescript
import { BiDirectionalMapper, type System, type CatalogField } from "@/components/mapper";
import "@/components/mapper/mapper.css";
```

### 2. Prepare Your Data

The mapper expects systems and their catalog fields:

```typescript
const sourceSystem: System = {
  id: "salesforce",
  name: "Salesforce",
  kind: "CRM",
};

const targetSystem: System = {
  id: "sap",
  name: "SAP ERP",
  kind: "ERP",
};

const sourceFields: CatalogField[] = [
  {
    id: "field-1",
    object_id: "obj-1",
    name: "account_id",
    label: "Account ID",
    data_type: "string",
    required: true,
    nullable: false,
    default_value: null,
    position: 0,
  },
  // ... more fields
];

const targetFields: CatalogField[] = [
  {
    id: "field-2",
    object_id: "obj-2",
    name: "customer_number",
    label: "Customer Number",
    data_type: "string",
    required: true,
    nullable: false,
    default_value: null,
    position: 0,
  },
  // ... more fields
];
```

### 3. Initialize Edges (Optional)

If you have existing edges from a previous integration, initialize them:

```typescript
const initialEdges = [
  {
    id: "edge-1",
    source: `system-${sourceSystem.id}`,
    target: `system-${targetSystem.id}`,
    sourceHandle: "output",
    targetHandle: "return-input",
    data: { direction: "outbound" },
  },
  {
    id: "edge-2",
    source: `system-${targetSystem.id}`,
    target: `system-${sourceSystem.id}`,
    sourceHandle: "response-output",
    targetHandle: "request-input",
    data: { direction: "inbound" },
  },
];
```

### 4. Render the Mapper

```typescript
<BiDirectionalMapper
  sourceSystem={sourceSystem}
  targetSystem={targetSystem}
  sourceFields={sourceFields}
  targetFields={targetFields}
  initialEdges={initialEdges}
  onEdgesChange={(edges) => {
    // Handle edge updates
    // Save to backend, update parent state, etc.
    console.log("Edges updated:", edges);
  }}
  onNodesChange={(nodes) => {
    // Handle node position changes
    console.log("Nodes changed:", nodes);
  }}
/>
```

## How to Replace IntegrationWorkspace with BiDirectionalMapper

If you want to use the mapper as a simplified integration editor for 2-node scenarios:

### Option A: Conditional Rendering

```typescript
export default function IntegrationWorkspace({
  onBack,
  initialIntegrationId,
  newIntegrationSystemId,
}: Props) {
  const [useSimpleMapper, setUseSimpleMapper] = React.useState(false);
  const [integration, setIntegration] = React.useState<Integration | null>(null);

  if (useSimpleMapper && integration?.source_system_id && integration?.target_system_id) {
    return (
      <div style={{ width: "100%", height: "100vh" }}>
        <BiDirectionalMapper
          sourceSystem={/* get from integration */}
          targetSystem={/* get from integration */}
          sourceFields={sourceFields}
          targetFields={targetFields}
          initialEdges={/* convert from integration.graph.edges */}
          onEdgesChange={(edges) => {
            // Update integration with new edges
          }}
        />
      </div>
    );
  }

  // Original IntegrationWorkspace UI for complex integrations
  return (
    // ... existing code
  );
}
```

### Option B: Separate Route/Component

Create a dedicated route for simple 2-node mappings:

```typescript
// src/pages/SimpleIntegrationMapper.tsx
import { BiDirectionalMapper } from "@/components/mapper";

export default function SimpleIntegrationMapper({ integrationId }) {
  // Load integration data
  // Load systems and fields
  // Render BiDirectionalMapper
}
```

## Converting Existing Integrations

If you want to convert existing `IntegrationWorkspace` graphs to `BiDirectionalMapper` format:

### Step 1: Extract Source and Target Nodes

```typescript
function extractEndpoints(graph: GraphDocument) {
  const sourceNode = graph.nodes.find(n => n.type === "source");
  const targetNode = graph.nodes.find(n => n.type === "target");
  return { sourceNode, targetNode };
}
```

### Step 2: Convert Edges

```typescript
function convertEdges(
  graph: GraphDocument,
  sourceNodeId: string,
  targetNodeId: string
) {
  return graph.edges
    .filter(edge => {
      // Only keep edges between source and target
      const isSourceToTarget =
        edge.sourceNodeId === sourceNodeId && edge.targetNodeId === targetNodeId;
      const isTargetToSource =
        edge.sourceNodeId === targetNodeId && edge.targetNodeId === sourceNodeId;
      return isSourceToTarget || isTargetToSource;
    })
    .map(edge => ({
      id: edge.id,
      source: edge.sourceNodeId === sourceNodeId ? `system-source` : `system-target`,
      target: edge.targetNodeId === targetNodeId ? `system-target` : `system-source`,
      sourceHandle: edge.sourcePortId,
      targetHandle: edge.targetPortId,
      data: {
        direction: edge.sourceNodeId === sourceNodeId ? "outbound" : "inbound",
      },
    }));
}
```

## Handle Naming Convention

When creating edges in your integration code, use these handle IDs:

### Source System (Left) Handles:
- **Outbound Outputs:** `output`, `output-secondary`
- **Request Inputs:** `request-input`, `request-input-secondary`

### Target System (Right) Handles:
- **Inbound Inputs:** `return-input`, `return-input-secondary`
- **Response Outputs:** `response-output`, `response-output-secondary`

### Field Mapping Example

When creating connections between specific fields:

```typescript
// Connect source field to target field
const edge = {
  id: `edge-sf-acct-id-to-sap-cust-num`,
  source: "system-salesforce",
  target: "system-sap",
  sourceHandle: "field:sf-acct-id",  // Format: field:{fieldId}
  targetHandle: "field:sap-cust-num",
  data: { direction: "outbound" },
};

// Connect response field back to source
const responseEdge = {
  id: `edge-sap-status-to-sf-status`,
  source: "system-sap",
  target: "system-salesforce",
  sourceHandle: "field:sap-status-code",
  targetHandle: "field:sf-status",
  data: { direction: "inbound" },
};
```

## Styling Customization

### Override Default Colors

In your CSS file:

```css
/* Outbound edges (Salesforce → SAP) */
.mapper-edge[data-direction="outbound"] {
  --edge-color: #3b82f6; /* Customize blue */
}

/* Inbound edges (SAP → Salesforce) */
.mapper-edge[data-direction="inbound"] {
  --edge-color: #8b5cf6; /* Customize green */
}

/* Custom handle styling */
.flow-handle {
  width: 14px;
  height: 14px;
  /* Customize handle appearance */
}
```

### Adjust Animation Speed

In `MapperEdge.tsx`, change the animation duration:

```typescript
const edgeStyle: React.CSSProperties = {
  animation: `${animationDirection === "reverse" ? "dash-animation-reverse" : "dash-animation"} 1.2s linear infinite`, // Change from 0.8s to 1.2s
};
```

## API Reference

### BiDirectionalMapper Props

```typescript
type BiDirectionalMapperProps = {
  // Required
  sourceSystem: System;
  targetSystem: System;
  sourceFields: CatalogField[];
  targetFields: CatalogField[];

  // Optional callbacks
  onEdgesChange?: (edges: Edge[]) => void;
  onNodesChange?: (nodes: Node[]) => void;

  // Optional initial state
  initialEdges?: Edge[];
};
```

### MapperEdge Props

The edge component automatically determines direction based on:
1. `data.direction` field ("outbound" or "inbound")
2. Handle naming (handles with "output" go outbound, "response" goes inbound)
3. X-coordinate comparison (sourceX < targetX = outbound)

### SystemNodeCard Props

```typescript
type SystemNodeData = {
  label: string;
  systemId?: string;
  objectId?: string;
  fields?: CatalogField[];
  isSource?: boolean;  // Enables outbound handles
  isTarget?: boolean;  // Enables inbound handles
};
```

## Troubleshooting

### Edges Not Routing Correctly

1. Verify handle IDs follow the convention (e.g., "output", "return-input")
2. Check that `isSource` and `isTarget` are set correctly on nodes
3. Ensure edge `data.direction` is set ("outbound" or "inbound")

### Animations Not Showing

1. Check CSS is imported: `import "@/components/mapper/mapper.css"`
2. Verify `strokeDasharray` is set on edges (default: "6 6")
3. Check browser console for CSS errors

### Handles Not Appearing

1. Verify `Position` enum is imported correctly
2. Check that `isSource` or `isTarget` is true on node data
3. Ensure `Handle` components are rendered within the node

## Next Steps

- Add field mapping UI in a drawer or modal
- Implement transformation nodes between source and target
- Add validation to prevent invalid connections
- Create a preview/test mode to validate mappings
- Export/import integration configurations

See [README.md](./README.md) for component-level documentation.
