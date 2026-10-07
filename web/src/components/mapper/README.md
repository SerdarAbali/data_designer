# Smart Bi-Directional Wiring & Auto-Routing for 2-Node Mapper

This implementation provides a sophisticated 2-node mapper with intelligent edge routing, directional theming, and smooth animations for seamless bi-directional data flow visualization.

## Components

### 1. **MapperEdge.tsx**
Custom edge component with smart routing logic and directional styling.

#### Features:
- **Dynamic Arc/Step Routing:**
  - **Outbound Edges (Left → Right):** Route through the upper canvas space with `-60px` offset
  - **Inbound/Response Edges (Right → Left):** Route through the lower canvas space with `+60px` offset
  - Automatic offset adjustment to prevent line overlapping

- **Directional Color Scheme:**
  - **Outbound:** Blue (`#2563eb`)
  - **Inbound/Response:** Emerald Green (`#10b981`)

- **Animated Dash Patterns:**
  - **Outbound Animation:** Dashes move left-to-right
  - **Inbound Animation:** Dashes move right-to-left (reversed)
  - Both use `strokeDasharray: '6 6'` with `0.8s` animation cycle

- **Visual Feedback:**
  - Selected edges highlight with `drop-shadow`
  - Edge labels display status with matching color scheme
  - Smooth transitions and hover effects

#### Usage:
```typescript
import { MapperEdge } from "@/components/mapper";

const edgeTypes = {
  "mapper-edge": MapperEdge,
};

// In your ReactFlow:
<ReactFlow
  edgeTypes={edgeTypes}
  edges={edges}
  // ... other props
/>
```

### 2. **SystemNodeCard.tsx**
Specialized node component representing source and target systems with multi-directional handles.

#### Handle Configuration:

**Left System (System A) - Source Node:**
- **Right Side (Position.Right):** 2 Outbound Output handles (`#2563eb` - Blue)
  - `output` (top 25%)
  - `output-secondary` (top 75%)
- **Top Side (Position.Top):** 2 Request Input handles (`#2563eb` - Blue)
  - `request-input` (left 25%)
  - `request-input-secondary` (left 75%)

**Right System (System B) - Target Node:**
- **Left Side (Position.Left):** 2 Inbound Return Input handles (`#10b981` - Green)
  - `return-input` (top 25%)
  - `return-input-secondary` (top 75%)
- **Bottom Side (Position.Bottom):** 2 Response Output handles (`#10b981` - Green)
  - `response-output` (left 25%)
  - `response-output-secondary` (left 75%)

#### Features:
- Clean card design with system name and field list
- Configurable for source-only or target-only modes
- Displays up to 5 fields with type information
- Responsive design for mobile screens
- Visual feedback on selection

#### Usage:
```typescript
import { SystemNodeCard } from "@/components/mapper";

const nodeTypes = {
  "system-card": SystemNodeCard,
};

const initialNodes = [
  {
    id: `system-${sourceSystem.id}`,
    type: "system-card",
    data: {
      label: `${sourceSystem.name} (Source)`,
      systemId: sourceSystem.id,
      fields: sourceFields,
      isSource: true,  // Enable outbound handles
    },
    position: { x: 50, y: 200 },
  },
  {
    id: `system-${targetSystem.id}`,
    type: "system-card",
    data: {
      label: `${targetSystem.name} (Target)`,
      systemId: targetSystem.id,
      fields: targetFields,
      isTarget: true,  // Enable inbound handles
    },
    position: { x: 600, y: 200 },
  },
];
```

### 3. **BiDirectionalMapper.tsx**
Complete 2-node mapper component with integrated edge and node management.

#### Features:
- Pre-configured for source and target systems
- Automatic node initialization
- Edge connection handling with direction detection
- Supports initial edges configuration
- Change callbacks for integration with parent components

#### Usage:
```typescript
import { BiDirectionalMapper } from "@/components/mapper";

export default function MyIntegration() {
  const sourceSystem = { id: "sys1", name: "System A", kind: "CRM" };
  const targetSystem = { id: "sys2", name: "System B", kind: "ERP" };

  return (
    <BiDirectionalMapper
      sourceSystem={sourceSystem}
      targetSystem={targetSystem}
      sourceFields={sourceFields}
      targetFields={targetFields}
      onEdgesChange={(edges) => console.log("Edges updated:", edges)}
      onNodesChange={(nodes) => console.log("Nodes updated:", nodes)}
    />
  );
}
```

## Edge Routing Logic

### Outbound Edge Path (Left → Right)
```
Source System A -------- Upper Arc ------> Target System B
```
- Uses `getSmoothStepPath` with `offset: -60`
- Borderradius: `20px`
- Color: Blue `#2563eb`
- Animation: Dashes move left-to-right

### Inbound/Response Edge Path (Right → Left)
```
Source System A <----- Lower Arc -------- Target System B
```
- Uses `getSmoothStepPath` with `offset: +60`
- Borderradius: `20px`
- Color: Green `#10b981`
- Animation: Dashes move right-to-left (reversed)

### Multiple Parallel Edges
When multiple edges connect the same node pair:
1. Automatic offset calculation prevents overlapping
2. Each edge uses slightly different curve parameters
3. Visual distinction maintained through handle positioning

## Styling

CSS classes provided in `mapper.css`:

- `.mapper-edge-label` - Edge label styling
- `.system-node-card` - Node card container
- `.system-node-header` - Node title area
- `.system-node-fields` - Fields list container
- `.flow-handle` - Handle base styling
- `.react-flow__edge[data-direction="outbound"]` - Outbound edge styling
- `.react-flow__edge[data-direction="inbound"]` - Inbound edge styling

### Custom Properties
- Outbound handles: Blue with `#2563eb` background
- Inbound handles: Green with `#10b981` background
- Handle hover effects with enhanced shadows
- Mobile-responsive design

## Example Integration

```typescript
import React from "react";
import { BiDirectionalMapper, type CatalogField, type System } from "@/components/mapper";
import "@/components/mapper/mapper.css";

export default function IntegrationExample() {
  const sourceSystem: System = {
    id: "salesforce",
    name: "Salesforce",
    kind: "CRM",
  };

  const targetSystem: System = {
    id: "sap",
    name: "SAP",
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

  return (
    <div style={{ width: "100%", height: "100vh" }}>
      <BiDirectionalMapper
        sourceSystem={sourceSystem}
        targetSystem={targetSystem}
        sourceFields={sourceFields}
        targetFields={targetFields}
        onEdgesChange={(edges) => {
          // Handle edge changes for saving
          console.log("Updated edges:", edges);
        }}
      />
    </div>
  );
}
```

## Performance Considerations

1. **Edge Routing:** Uses `getSmoothStepPath` for optimal performance (vs. complex Bezier paths)
2. **Animation:** CSS-based animations (no JavaScript frame updates)
3. **Handle Positioning:** Static positions with CSS, no dynamic calculation on every render
4. **Field List:** Limited to 5 visible fields with overflow indicator

## Browser Compatibility

- Works with all modern browsers supporting:
  - CSS Grid/Flexbox
  - SVG Path rendering
  - CSS Animations
  - ES2020+ JavaScript

## Future Enhancements

- Support for multi-hop routing (3+ node mappers)
- Custom curve types (Bezier, Cubic, etc.)
- Animated flow indicators
- Edge weight visualization
- Field type mismatch indicators
- Validation rule visualization
