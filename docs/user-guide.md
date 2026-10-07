# Data Designer — User Guide

This guide is for people who design and document integrations in Data
Designer. It explains the concepts, walks through every workspace, and ends
with a hands-on tutorial. For installation and development, see the
[README](../README.md).

> **Design-time only.** Data Designer never connects to your real systems.
> Every test, preview, and scenario evaluation runs the built-in
> transformation engine against sample data you provide. Nothing is sent
> anywhere, and nothing is scheduled or executed.

## Contents

1. [Concepts](#1-concepts)
2. [Signing in and finding your way around](#2-signing-in-and-finding-your-way-around)
3. [Catalog](#3-catalog)
4. [Contract Designer](#4-contract-designer)
5. [Landscape](#5-landscape)
6. [Scenarios](#6-scenarios)
7. [Tutorial: from catalog to sequence diagram](#7-tutorial-from-catalog-to-sequence-diagram)
8. [Limits, rules, and FAQ](#8-limits-rules-and-faq)

---

## 1. Concepts

| Term | Meaning |
|---|---|
| **System** | Any application or platform that holds data, e.g. a CRM or ERP. Systems are generic: there are no vendor-specific types. |
| **Object** | A data structure inside a system, e.g. `Customer` or `Invoice`. |
| **Field** | A single attribute of an object, with a free-form data type such as `string`, `integer`, `boolean`, `date`. Each field has a permanent ID, so renaming it never breaks mappings. |
| **Contract** | A designed integration from a **source** (System A, the initiator) object to a **target** (System B, the receiver) object. Called *integration* in the API. |
| **Interaction type** | How the two systems talk: **One way**, **Request / response**, or **Async callback**. |
| **Phase** | One direction of a contract's exchange: **Request** (A → B), **Success response** (B → A), **Error response** (B's error object → A), or **Async response** (B → A later). Each phase has its own mapping graph. |
| **Mapping graph** | Wires from sender fields to receiver fields, optionally through transformation nodes (functions, concatenation, lookups…). |
| **Sample data / test data** | Example rows you type or generate to test a mapping. They exist only for design and testing. |
| **Scenario** | A documented interaction (happy path, alternative, or error) made of ordered steps that reference contract phases. It is drawn as a UML sequence diagram. |
| **Archive** | Deleting is always a soft archive: records disappear from lists but are kept. |

Which phases a contract has depends on its interaction type:

| Interaction type | Phases |
|---|---|
| One way | Request |
| Request / response | Request, Success Response, Error Response |
| Async callback | Request, Async response (shown as *Response (async callback)*) |

---

## 2. Signing in and finding your way around

Open the address your administrator gave you (for example
`http://10.0.0.51:5173`) and sign in with your email and password. There is a
single internal account and no self-registration.

The header contains the workspace navigation and the **Account menu** (your
email and tenant, with sign-out):

| Tab | Purpose |
|---|---|
| **Catalog** | Model systems, objects, and fields. |
| **Contracts** | Design contracts: mappings, test data, settings, scenarios. |
| **Landscape** | See all systems and contracts as a map, trace field lineage, and write end-to-end scenarios. |

---

## 3. Catalog

The Catalog has three panels: the **Systems** tree on the left, a designer
in the middle (System, Object, or Field Designer), and a contents table for
the selected item's children.

### Systems

- **＋ Add system** creates a system. **Filter catalog tree** searches systems,
  objects, and fields.
- In the **System Designer**, the **General** tab edits *System name*, *Kind*
  (free text such as `application` or `database`), *Description*, *Icon*,
  *Color*, and *Position X/Y* (its spot on the Landscape). Click
  **Save system**.
- **Raw metadata JSON** stores any extra structured notes, up to 16 KiB.
- **Archive system** archives the system together with its objects and fields.

### Objects

- From a system, **＋ Add object** opens a small dialog. The **Objects** table
  lists name, label, and field count; **Open object** opens the Object
  Designer.

### Fields

- From an object, **Add field** opens a dialog. Each field has:
  - *Name* (technical, used in CSV files) and *Label* (display text).
  - *Data type*: free text. The test engine understands `string`/`text`,
    `number`/`float`/`decimal`, `integer`/`int`, `boolean`/`bool`, `date`,
    `datetime`, `object`/`json`, and `array`. Other values are allowed in
    the catalog but fail when tested.
  - **Required**, **Not null**, **External identifier**, **Origin**,
    **Position**, and **Description**. Fields also have a default value,
    which can be set through the API but not in this dialog.
- Use **Move up** / **Move down** to change field order.

### Archiving rules

You cannot archive a system, object, or field while an active contract uses
it. The app lists the contracts that block the archive; remove the mapping
or archive the contract first. Scenarios never block archives (see
[§6.8](#68-missing-references)).

---

## 4. Contract Designer

Open **Contracts**. Use **Switch contract** to pick a contract, or choose
**+ New contract**.

### 4.1 Creating a contract

In **Create a contract**, choose the **Source** system and object (System A,
the initiator) and the **Target** system and object (System B, the receiver),
give the contract a name, then click **Create contract**. New contracts are
**One way** by default.

### 4.2 The contract header

| Control | What it does |
|---|---|
| **← Back** | Return to the contract list. |
| **Switch contract** | Jump to another contract. Unsaved changes are confirmed first. |
| Save state (e.g. *Saved · r35*) | Shows whether there are unsaved changes and the current revision. |
| **Reload Schema** | Re-read the catalog fields, for example after you added fields in the Catalog. |
| **Preview Payload** | Show the payload the current phase would produce from the test data. |
| **Interaction** | Switch between **One way**, **Request / response**, and **Async callback**. |
| **Save** | Save all phases, test data, and settings together. |
| **⋯** | **Contract settings**, **Design validation**, **Import CSV**, **Export CSV**, **Download CSV template**, **Preview Payload**. |

**Contract settings** opens a side drawer with:

- **Contract name**.
- **Error response schema**: for Request / response contracts, pick the
  existing object in System B that represents an error. No schema is
  generated. The Error Response tab stays empty until you pick one.
- **Contract Dependencies**: declare that this contract depends on another
  contract (upstream → downstream). This is documentation only; it does not
  schedule anything. Cycles and self-dependencies are rejected.

### 4.3 Tabs

- **Overview**: a diagram of System A and System B with each phase's
  direction, plus a **Contract summary** (source, target, interaction
  pattern, save state, design validation, dependencies).
- **Request**, **Success Response**, **Error Response**, or
  **Response (async callback)**: the mapping workbench for that phase. Each
  phase has its own independent graph. Response phases map from System B's
  object back to System A's object.
- **Scenarios**: scenarios for this contract (see [§6](#6-scenarios)).

### 4.4 Mapping workbench

The toolbar above the canvas offers:

| Control | Use |
|---|---|
| **Canvas** / **Mapping Matrix** | Graphical canvas, or a table of sender field → receiver field rows with filters. |
| **Add transformation** | Insert a node: **Constant**, **Function**, **Concatenate**, **If / else**, **Map**, **Coalesce**, **Lookup**, **Filter**, **Validate**. |
| **Auto-map** | Connect fields with the same name one-to-one. |
| **Test data** | Open the sample-data drawer (see [§4.5](#45-test-data-and-results)). |
| **Errors** | List validation errors and warnings for this phase. |
| **Reset layout**, **Fit view**, **−**/**+** | Tidy and zoom the canvas. |

**Mapping fields.** Drag from a sender field handle to a receiver field
handle. A direct connection needs the same data type on both sides. If the
types differ, the editor marks the mismatch and can offer to insert a
suitable conversion (for example `toInt`) automatically. Each receiver field
accepts only one incoming mapping.

**Adding and editing fields in place.** The source and target nodes can
create, edit, and remove fields on their objects directly; the new handle
appears immediately. Removing a field warns you if mappings use it.

**Transformation nodes.** Select a node to configure it in the inspector.

| Node | Purpose |
|---|---|
| Constant | Emit a fixed value. |
| Function (`fx`) | Apply one function from the table below. |
| Concatenate | Join several inputs as text, in connection order. |
| If / else | Choose between two inputs using a boolean condition input. |
| Map | Translate exact values via a key → value table, with an optional fallback. |
| Coalesce | First input that is neither missing nor null. |
| Lookup | Translate via a local table; a miss uses the fallback or fails. |
| Filter | Takes a boolean input: `true` lets the row continue, `false` marks the row skipped. |
| Validate | Check `required`, `type`, `min`/`max`, or `allowedValues`; pass the value on unchanged. |

| Function | Effect |
|---|---|
| `trim`, `lower`, `upper`, `title` | Whitespace and casing for text. |
| `toInt`, `toNumber`, `toString`, `toBoolean` | Explicit type conversion. |
| `parseDate` | Parse text with an *input format* into ISO date/datetime. |
| `formatDate` | Format an ISO date/datetime with an *output format*. |
| `date` | Legacy: input and output format in one step. |
| `e164` | Normalise a phone number to E.164; national numbers need a *country calling code*. |

Each node has an error policy: **fail** (default; the row fails), **skip**
(omit the value), or **default** (use a configured default). There is no
custom code or expression language.

### 4.5 Test data and results

**Test data** opens the sample-data drawer for the current phase:

- **Sample payload rows**: edit rows in **Form / Table** or **Raw JSON**
  view. Use **+ Add row**, remove rows, or **Generate Sample Data** to create
  rows from field names and types. Up to 100 rows.
- **Run test** runs the phase's graph through the engine. Tests also run
  automatically, debounced, while you edit.
- **Latest test result** shows each row's outcome. Choose a **Result row**
  to see its **Target values** and the **Node trace**, i.e. the value at
  every node. The canvas nodes also show their latest values.
- For Request / response contracts, **Mock response payload** lets you
  type System B's response JSON to test the reverse mapping.

Test data is saved with the contract. Values never leave the app.

### 4.6 Saving and conflicts

**Save** stores every phase graph, the interaction type, test data, and the
name in one revision. If someone else saved the contract in the meantime,
the save is rejected with a revision conflict; reload, then reapply your
changes. Switching contracts with unsaved changes asks for confirmation.

### 4.7 CSV import and export

Open a mapping phase tab, then use **⋯** → **Import CSV**, **Export CSV**,
or **Download CSV template**. CSV exchange covers field mappings only. It is
not a backup, and it does not import business data or create catalog fields.

Columns:

```text
format_version,source_field,target_field,transformation,error_policy,input_format,output_format,country_calling_code
```

- `format_version` is `1`. Use exact catalog field **names**, not labels.
- Source and target follow the active tab's direction; response tabs are
  reversed.
- A row is either a direct mapping (blank `transformation`; identical data
  types) or one function from the table in [§4.4](#44-mapping-workbench).
  `error_policy` is `fail` (default) or `skip`.
- Version 1 cannot express chains, shared nodes, constants, other node
  types, or the `default` policy. Export refuses rather than silently
  dropping such mappings.

**Import** shows a preview. You can map custom column headers and resolve
unknown or ambiguous field names. **Add only** (default) leaves exact
duplicates alone and blocks conflicting targets. **Replace matching targets**
replaces only the listed targets. Nothing is applied partially; you can
download an issue report. Confirmed changes go into the draft. Review them,
then click **Save**. **Undo import** works until your next edit, save, or
phase change.

File rules: UTF-8, at most 1 MiB and 500 rows; comma, semicolon, or tab
delimiters. Export writes UTF-8 with BOM and CRLF. In spreadsheets, format
the columns as **Text**. Cells that look like formulas are rejected.

---

## 5. Landscape

**Landscape** shows the whole architecture. The metric bar counts
**Systems**, **Contracts**, **Contracts with errors**,
**Contracts with warnings**, and **Incomplete contracts**. Use the view
switch at the top:

### 5.1 Systems

A map of systems connected by contract routes. Filter by **Search**,
**System kind**, **Interaction** pattern, **Validation** status, and
**Relative direction** (Upstream or Downstream of the selection). Drag
systems to arrange them (positions are saved), or use **Auto-layout**,
**Fit**, and **Lock**. Select a system to see its objects and incoming and
outgoing contracts.

### 5.2 Contracts

Select a directed contract edge to inspect its phases, validation status,
mappings, and dependencies, then open it in the Contract Designer.

Contract health:

- **Draft / incomplete**: no receiver fields mapped yet.
- **Attention**: two contracts write the same target field, or an upstream
  dependency is unhealthy.
- **Healthy**: mapped, with no known conflicts.

### 5.3 Field Lineage

**Trace a field across contracts**: search for a field, choose
**Direction** (Upstream, Downstream, Both) and **Maximum depth** (1–5 hops).
Lineage follows exact field IDs through mappings; matching names are never
treated as the same field. It is read-only.

### 5.4 Scenarios

End-to-end scenarios that span several contracts (see [§6](#6-scenarios)).

### 5.5 Advanced

**Advanced** → **Legacy Hybrid (advanced)** expands systems into their
mapped fields and transformations, filtered by phase. Use **Refresh** to
reload landscape data.

---

## 6. Scenarios

A scenario documents one concrete story, such as "customer created" or
"billing rejects duplicate account". Each scenario is shown as a UML
sequence diagram. Scenarios **reference** contracts; they never copy or change
them.

### 6.1 Where scenarios live

| Place | Scope | Shows |
|---|---|---|
| Contract Designer → **Scenarios** tab | Contract scenarios (one contract) | This contract's scenarios **and** any end-to-end scenarios that use it |
| Landscape → **Scenarios** | End-to-end scenarios (many contracts) | All end-to-end scenarios |

Both use the same editor and diagram. The list groups scenarios as
*Contract scenarios* and *End-to-end scenarios*.

### 6.2 Creating and managing

- **New scenario** creates a draft named *New contract scenario* or
  *New end-to-end scenario*. In the contract tab the current contract is
  already a participating contract.
- **Save** stores it. *Unsaved* marks pending changes, and **Discard**
  reverts them.
- **Duplicate** copies a saved scenario as "… (copy)".
- **Delete** archives the scenario after confirmation.
- Scenario names must be unique.

### 6.3 Scenario details

| Section | Content |
|---|---|
| Name, category | **Happy path**, **Alternative**, or **Error**. Optional business description. |
| **Preconditions** | What must be true before the scenario starts. |
| **Trigger** | What starts it (e.g. "User submits signup form"). |
| **Participants** | Systems (**+ System…**) and free-text **Actors** such as *User*. They become lifelines, in this order. Systems used by contract steps are added as lifelines automatically, so add participants only to set the order or to include actors. |
| **Participating contracts** | Contracts available to contract steps. |
| **Before state** / **After state** | Example field values per system object, before and after the scenario. |
| **Message steps** | The ordered interaction (below). |
| **Assertions** | Statements to check. Link an assertion to a step and field with an expected value to check it automatically; otherwise it is a **Manual check**. |
| **Notes** | Free text. |

### 6.4 Steps and blocks

Add steps with **+ Contract step**, **+ Self call**, or
**+ Actor / free message**:

| Type | Drawn as | Details |
|---|---|---|
| **Contract** | Arrow between the contract's systems | Pick a contract and **phase**. The sender and receiver come from the contract; you cannot draw it in the wrong direction. Requests are solid arrows; responses are dashed returns. New contract steps default to a participating contract that no step uses yet. |
| **Self** | Arrow looping back to one lifeline | *Internal processing* in one participant. |
| **Actor / free message** | Arrow between any two participants | Free-text message, e.g. a user action. Needs at least one participant. |

A contract step can also carry:

- **Sample values (sender)**: input values for evaluation.
- **Expected response (receiver)**: values you expect the mapping to produce.

Each step and block has **↑**/**↓** (move up or down), **Duplicate**,
and **Remove**. **Wrap in…** puts a step inside a block; **Unwrap**
dissolves a block and keeps its steps.

| Block | Meaning |
|---|---|
| `alt` | Alternatives. Wrapping creates two branches, the second with guard `else`. **+ Branch** adds more. Each branch has its own add-step buttons. A branch after the first with an empty guard is drawn as `[else]`. |
| `opt` | Optional: runs only if its guard holds. |
| `loop` | Repeats, e.g. `[for each order line]`. |

Type the guard condition in the block's guard box; an empty guard is drawn
without brackets. You can change a block's type later with **Block type**.
Blocks can be nested up to three levels deep.

### 6.5 Sequence Diagram and Steps views

Switch with the **Scenario view** toggle:

- **Sequence Diagram**: generated and read-only. It shows lifelines,
  numbered messages labelled with the contract and phase, self-calls, and
  `alt`/`opt`/`loop` frames. **Click a contract message** to open that
  contract at that phase in the Contract Designer.
- **Steps**: the editor described above.

### 6.6 Evaluating samples

**Evaluate samples** runs each contract step's sample values through that
contract's **saved** mapping for the chosen phase, using the same engine as
**Run test**. It compares the result with the expected values and checks
the assertions. The **Sample evaluation** bar shows *ok*, *mismatched*, and
*failed* counts and assertion results; the diagram and step rows show
per-step markers.

Possible step outcomes: **ok**, **mismatch** (the produced value differs
from the expected value), **failed** (the mapping raised an error),
**skipped**, **missing reference**, **not evaluated** (no sample values, or
a self or actor step).

Evaluation never saves anything or contacts a system. Because it uses saved
contracts, save contract changes first.

### 6.7 What scenarios never do

- Change a contract's mappings, schemas, or test data.
- Run, schedule, or call real systems.

### 6.8 Missing references

You may archive a system, contract, or field that a scenario uses. The
scenario keeps the reference and shows a **Missing references** warning
(for example *Archived or moved*, *Missing object*, *Missing field*). Edit
the affected steps, or restore the archived item.

---

## 7. Tutorial: from catalog to sequence diagram

This walkthrough builds a small CRM → ERP customer sync, tests it, and
documents a happy path and an error scenario. Names in *italics* are
suggestions.

### Step 1 — Model the systems

1. **Catalog** → **＋ Add system**: *Tutorial CRM*, kind `application`.
   **Save system**.
2. **＋ Add object**: *Customer*. Open it and **Add field**:
   - `name`, data type `string`, Required
   - `email`, data type `string`
3. Add a second system, *Tutorial ERP*, with object *Account* and fields
   `accountName` (`string`, Required) and `accountId` (`string`).
4. In *Tutorial ERP*, add an object *AccountError* with field
   `message` (`string`) to represent error replies.

### Step 2 — Create the contract

1. **Contracts** → **Switch contract** → **+ New contract**.
2. Source: *Tutorial CRM / Customer*. Target: *Tutorial ERP / Account*.
   Name it *Tutorial customer sync*. **Create contract**.
3. Set **Interaction** to **Request / response**.
4. **⋯** → **Contract settings** → **Error response schema**: *AccountError*.

### Step 3 — Map the request

1. Open the **Request** tab.
2. **Add transformation** → **Function**; in the inspector choose `upper`.
3. Connect `name` → Function → `accountName`.
4. Click **Errors** and check that nothing is reported.

### Step 4 — Map the responses

1. **Success Response** tab: the ERP *Account* is now the sender. On the
   CRM (receiver) node, add a field `erpId` (`string`) and connect
   `accountId` → `erpId`.
2. **Error Response** tab: add `syncError` (`string`) on the CRM node and
   connect `message` → `syncError`.

### Step 5 — Test and save

1. On the **Request** tab, open **Test data** → **+ Add row**. Enter
   `name = acme corp`.
2. **Run test**: **Target values** shows `accountName = ACME CORP`.
3. Click **Save**. The save state shows the new revision.

### Step 6 — Happy-path scenario

1. Open the **Scenarios** tab → **New scenario**. Name it
   *Customer created*, category **Happy path**.
2. **Trigger**: "Sales rep saves a new customer". **Preconditions**:
   "Customer does not exist in ERP".
3. Under **Message steps**:
   - **+ Contract step**: *Tutorial customer sync*, phase **Request**, with
     **Sample values (sender)** `name = acme corp` and
     **Expected response (receiver)** `accountName = ACME CORP`.
     *Tutorial CRM* and *Tutorial ERP* appear as lifelines automatically.
   - **+ Self call**: choose *Tutorial ERP*, label "Create account".
   - **+ Contract step**: same contract, phase **Success response**.
4. Add an **Assertion** linked to the first step and the `accountName`
   field, expecting `ACME CORP`.
5. **Save**, then **Evaluate samples**: the steps show **ok** and the
   assertion passes.
6. Switch to **Sequence Diagram**: two lifelines, a request arrow, a self
   call, and a dashed return. Click the request arrow and the Request tab
   opens.

### Step 7 — Error scenario with `alt`

1. Select *Customer created* → **Duplicate**, rename the copy to
   *Customer rejected*, category **Error**.
2. On the **Success response** step choose **Wrap in…** → `alt`. Type
   `accepted` as the first branch's guard.
3. In the second (`else`) branch, use **+ Contract step** with phase
   **Error response**.
4. **Save** and view the diagram: an `alt` frame with `[accepted]` and
   `[else]` branches.

### Step 8 — End-to-end view

If a second contract continues the flow (for example ERP → Billing), open
**Landscape** → **Scenarios** → **New scenario**. Add both contracts as
participating contracts and chain their steps. Clicking any message opens the
right contract. The existing *Demo* systems and *Onboard customer
end-to-end* scenario are a ready-made example.

---

## 8. Limits, rules, and FAQ

### Limits

| Item | Limit |
|---|---|
| Test data | 100 rows, 64 KiB per contract |
| Mapping graph | 200 nodes, 500 edges, 256 KiB; 8 KiB per node config |
| CSV import | 1 MiB, 500 rows |
| Scenario | 200 steps, 30 participants, 50 contracts, 200 assertions, blocks nested 3 deep, 256 KiB |
| System metadata JSON | 16 KiB |

### FAQ

**Why can't I connect two fields?** Direct connections need identical data
types. Insert a **Function** conversion, or accept the suggested conversion.

**My new catalog field isn't on the canvas.** Click **Reload Schema**.

**The Error Response tab is empty.** Pick an **Error response schema** in
**Contract settings**.

**Evaluation shows old results.** Scenarios evaluate the **saved** contract.
Save the contract first.

**I renamed a field. Are mappings and scenarios broken?** No. Everything
references permanent field IDs; only the displayed name changes.

**I can't archive a field.** An active contract maps it. The error lists the
contracts involved.

**Can Data Designer push data into my systems?** No. It is a design tool
only. Connectors, credentials, scheduling, and runtime execution are not part
of the product.

**Where is my data stored?** In the app's PostgreSQL database, scoped to
your tenant. Test values are not logged.
