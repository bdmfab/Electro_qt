# Electro_qt (early canvas)
    pip install PySide6      (Linux: sudo apt install libxcb-cursor0)
    python run_electro.py
Tools: V select, L line, R rect, C circle, D dot, T text, X trim, F fillet, H chamfer.
After a command finishes you are back in Select. Right-click empty space, Space or Enter repeats the last command.
Space = Enter everywhere (commits a typed length / radius). Esc cancels.
Fillet/Chamfer work on lines and rectangle edges (a rectangle becomes four lines). Click the part of each line to keep. Type a value + Enter/Space to change the radius; chamfer takes "0.25" or "0.25,0.4" (distance on 1st line, 2nd line).
Layers... (Ctrl+L): user-made; tick "Wire layer" to get the numbering options.
Grid is centred on the row lines; View > Grid divisions sets lines between rows (default 1).
F7 grid, F8 ortho, F9 grid snap, F3 object snap. Wheel zoom, middle-drag pan, Home = fit.
Tests: python -m pytest tests

Right-click menu (in Select): on an item or on blank space while something is selected.
  Group (2+ selected), Ungroup, Resize (one group selected), Delete, Repeat <last command>.
  Right-click blank space with nothing selected still repeats the last command.
Resize: four grips at the middle of each side; drag one to move that side perpendicular to itself.
  Neighbouring lines stretch, corner arcs keep their radius, snaps to grid, each drag is one undo step.
  Esc / Enter / Space / right-click / click away finishes.

Align (right-click with 2+ selected > Align): left, right, top, bottom, center, middle; Distribute needs 3+.
Multiline (M): parallel wires, one layer each from the active preset (default 3ph+PE = L1 brown, L2 orange,
  L3 yellow, PE green). Presets...: edit layers/spacing. Missing layers are offered for creation.
Text: font / height / color on the second toolbar; right-click selected text > Text properties...
Layers: color (incl. brown, orange) and line weight (Default = the original look). View > Background.


## Title block, sheets, editing, color standards
- **Sheets**: one tab per sheet (Sheet menu: add from template, delete, Title block...). Templates are 11x17 landscape, 1-column (zones 00-24) or 2-column (00-49), built from the sample DXFs (hexagon zone ruler, JOB / DRAWN / DATE / TITLE 1-4 / PAGE n OF m). The logo box is left empty.
- **Grid** now sits on the true row centres (y = 9.45 - 0.35*i), x origin 0.
- **Copy / Cut / Paste** (Ctrl+C/X/V, clipboard shared across sheets; paste = click to place with ghost), **Rotate** (Ctrl+R / Ctrl+Shift+R / custom; rectangles 90 deg only), **Mirror** (Ctrl+M left-right, Ctrl+Shift+M top-bottom). All also in the right-click menu.
- **Color standards** (toolbar combo + Standards...): named by you (defaults 480 VAC, 240 VAC, 120 VAC). Each wire has label, layer and color. Pick one and use Multiline (M); layers are created automatically.

## Version 0.6.0 additions
- **Help > About** shows the version (`electro.__version__`).
- **Properties panel** (docked right): layer, color override (By layer or any palette color), line-weight override, and for text: font, height, justification. Works on groups (applies to children); mixed values show "varies". One undo step per change. Moving a line to/from a numbered wire layer adds/removes its wire-number slot.
- **Text justification**: left / center / right (toolbar for new text, panel for existing).
- **Array** (Edit > Array..., Ctrl+Shift+A, right-click): linear (rows x columns, spacing) or polar (count, fill angle, center, rotate copies). Optional: increment the trailing number in text per copy with a step (`TB09` -> `TB10`). Wire numbers are not touched.
- On hold pending discussion: text styles, rich multiline text, line/circle grips.

## Text styles and grips (0.6.x)
- **Text styles** (toolbar dropdown + Styles...): named font / height / color / justification, "Default" = the old settings. New text uses the dropdown style; the Properties panel assigns a style to selected text (replacing the old per-text font/height controls). Editing a style updates every text using it (undo history is cleared when that happens); deleting a style moves its text to Default. These are for simple text; rich multiline text will be a separate object.
- **Line grips**: select a line and the whole joined run shows a mid grip on every segment and an end grip on each open end only. Dragging a mid grip moves that segment perpendicular to itself and the joined segments stretch to follow (vertical-horizontal-vertical works). Dragging an end uses snap/ortho. Esc cancels a drag.
- **Circle**: one grip at the bottom sets the radius; Radius is also in the Properties panel.

## 0.6.x notes
- Toolbar: Standards... / Styles... buttons sit left of their dropdowns.
- Text justification now applies to every line of a multi-line text (text is drawn as a path), with the anchor at the block's left edge / middle / right edge.
- Clicking an object no longer nudges it: it must be held 300 ms before it can be dragged (CLICK_DELAY in scene.py). Box-select from blank space is not delayed.
- Sheet > Title block image... places a picture (PNG/JPG, kept inside the project, scaled to fit) in the logo box on every sheet; Remove title block image clears it.
- App icon: electro/ui/resources/icon.png (also icon.ico for packaging).

## Blocks and library (0.7.0)
- **Slot tool (S)**: while drawing a part, click each place a wire lands and name the terminal (names count up: 1, 2, ...). Double-click a slot to rename it.
- **Make block** (Ctrl+B / right-click): select the drawing + its slots, give name, description, part number, manufacturer, hyperlink, tag prefix, poles, wire-number increment, letter rule, and which label lines to stack beside it ({description}, #{part}, {tag}). Rectangles are exploded into lines so blocks can rotate. The selection is replaced by one instance. Field codes in block text: {tag} {description} {part} {part_label} {manufacturer}.
- **Library dock** (left): Place (or double-click), Data..., Delete, Import/Export a `.eqlib` file to reuse parts in other projects.
- **Placing**: click to drop; Ctrl+R / Ctrl+M turn / flip the ghost first. Wire-layer lines running through the block's slots are trimmed to the slots (multi-pole blocks trim every wire at once). Wire ends snap to slots.
- **Device tags** = prefix + page + zone, then A, B... if taken. Edit in Properties (a typed tag is kept as manual). Sheet > Update device tags... recomputes automatic ones.
- Not yet: rubber-banding wires when a block moves, wire numbering, per-instance terminal text editing, bundle-aware pole matching.

## 0.7.1: editing placed parts
- Stacked label now sits ABOVE the part by default (tag nearest the part, description on top). Library > Data... switches it to the right side and chooses the lines; this rebuilds the label text of that block.
- **Double-click a placed part** (or right-click > Part properties..., or the button in Properties) to edit that one part: description (starts as the block's), part number, manufacturer, tag, which label lines show, and each terminal name. Edits are per part and undoable.
- **Tag > Pick...** opens a table of every placed block; choosing one copies its tag (e.g. a contact takes its coil's tag). A tag you type or pick is manual and survives Update device tags.
- **Pair numbering...** fills terminals as pairs (13/14, 23/24 ... or 1/2, 3/4 ...); every cell stays editable.
- Update device tags lists tags used more than once as a warning (expected for a coil and its contacts).

## 0.7.2
- **Tag letters**: A, B ... are added only when another AUTOMATIC tag has the same prefix, page and zone (same row). A typed or picked tag never forces a letter on the coil.
- **Linked tags**: Pick... in Part properties links the part to the chosen block. Sheet > Update device tags... recomputes the coil's tag from its new position and the linked parts follow; typing a different tag breaks the link. Links to deleted blocks are reported.
- **Library folders**: the library dock is a tree. New folder / Rename / Delete folder (blocks move up a level); Data... or Make block choose the folder.
- **Copy (rename)...**: duplicates a block definition under a new name into any folder (placed parts keep the original).
- **Import / Export** (.eqlib): import into the selected folder (name clashes are renamed "Name (2)"); export one block, one folder (with sub-folders and empty folders), or the whole library.

## 0.7.3: shared block library on disk
- The library is the folder **`blocks`** next to `run_electro.py` (created on first start). One `.eqblock` XML file per block; sub-folders are library folders. Library > Library folder... points it somewhere else (e.g. a network drive); "Use the default library folder" goes back. The choice is remembered per user.
- The library dock shows that folder. Make block saves the new block there (in the folder you choose) and in the project. Placing a block copies its definition into the project, so project files still open without the library. "This project only" lists blocks that are not in the library (e.g. from a DXF import): right-click > Save to shared library...
- Data..., Copy (rename)..., Delete, New/Rename/Delete folder, Import/Export (.eqlib) all act on the library files. Data... also updates this project's copy.
- Library > Update project blocks from library... replaces a project's copies with the library versions (placed parts change). Reload library re-reads the folder; unreadable files are listed and never deleted.

## 0.8.0: wire numbering
- Slot terminal names now print BELOW each slot.
- **Mark wire** (right-click a wire): the start of numbering, with a start incident (AC schemes default to 1, others 0). An orange diamond shows it. **Clear wire mark** removes it.
- **Sheet > Update wire numbers (F5)** numbers every wire reachable from a mark, on all sheets, as one undo step per sheet. Numbers are drawn beside the middle of each wire (above horizontal, left of vertical); orange = override/locked.
- **Wire number...** (right-click): Automatic / Override (your number, sequence continues) / Locked. Applies to the whole wire (every connected segment).
- **What is one wire**: lines on the same layer that touch end to end, end on the side of another line, or cross at a solid dot (a plain crossing is NOT connected). Different layers never join. Blocks separate wires; slots are taken in pairs (1-2, 3-4...), each pair is one pole that passes the run on.
- **Number rules**: per layer scheme with <page> <zone> <col> <incident> <L|T> <phase>. Page/zone come from the wire's LEFT end. <incident> = start + number of +1 blocks passed outward from the mark. <L|T> is T when the wire touches a block whose letter rule is "motor". <phase> is the layer's phase (L1 -> 1). PE and un-numbered layers are skipped. Lead-zero suppression is a project flag.
- **Warnings** (never errors): wires not reached from a mark, duplicate numbers, two routes giving different numbers, incident above 9. Gotos, wire list and label export come next.

## 0.8.1
- Library: Data and Copy buttons removed (right-click menu keeps them; Delete is in the block and folder menus and on the Del key). Panel minimum width halved.
- Toolbar widths: layer box +50%, Standards -20%, Styles -30% (constants at the top of ui/main.py).
- **Explode block** (right-click / Edit > Explode block, Ctrl+Shift+X): the part becomes plain drawing objects (text frozen, hidden lines dropped) plus slot marks, so it can be edited and made into a block again.
- **Block origin**: Make block asks for the origin: a slot (the first by default), the selection centre, or "Pick a point on the drawing...". The origin lands on the cursor when the block is placed.
- **Letter rules** (Sheet > Letter rules...): name, pattern (e.g. <L|T>), result if true, result if false. A block's Letter rule is chosen from this list; wire numbering uses the table instead of the fixed motor rule (default row: motor <L|T> T L).

## 0.8.2: hops, dots, auto-trim
- Crossing wires: the more vertical wire hops over the other, drawn on screen only. A solid dot on the crossing connects instead.
- Right-click a crossing: "Connect wires here (dot)" or "Hop (remove connection dot)".
- A wire end landing on the side of a same-layer wire (or 3+ ends meeting) gets an automatic dot (graphical).
- Multiline: each wire's first segment is trimmed back to start at its own-layer bus (L2 starts at the L2 line, L3 at the L3 line); a wire already starting on its bus is untouched.

## 0.8.3: global incident, scheme builder
- New scheme part `<g_incident>`: a global count 1, 2, 3 ... over all wires using it, page by page, left to right then top to bottom. No Mark wire is needed.
- Layers dialog: the Scheme box lists the built-in schemes (AC, DC, Global), your own, and "New...". New opens a builder: pick parts from the list (page, zone, col, incident, g_incident, phase and every Letter-rule pattern), add fixed text, reorder, name it. Saved with the project.

## 0.8.4: `<phase_incident>`
Scheme part for AC drawings: one number per *set* of parallel phase wires, so L1/L2/L3 of a run share it (`1L1 1L2 1L3`, then `2L1 2L2 2L3` after the next incrementing block). A set = nets on the same side of one block, nets drawn together as a multiline, and both sides of a non-incrementing block. Counting goes depth-first from the marked wire (or the top-left set): finish one branch before starting the next, top branch first. The counter is global across pages. Built-in scheme "AC sets" = `<phase_incident><L|T><phase>`.

## 0.8.5
- Layers auto-created for a multiline use the AC sets scheme (`<phase_incident><L|T><phase>`).
- Wire numbers can be clicked (select the wire), double-clicked (edit) or right-clicked. New number mode **Ignore**: never numbered automatically, type a number if you want one. Any wire-layer line (PE too) can be given a number by hand with right-click > Wire number...; update never changes it.
- Trim works on circles: the clicked part is cut out between the nearest crossings and the rest becomes an arc.
- Library right-click > Edit library...: opens the `blocks` folder; OK reloads, Cancel does not.
- The window opens maximized.

## 0.8.6
- **Arc tool (A):** click the two ends, then move the center; the radius follows and stops at a half circle. The arc bulges away from the center, so moving the center across the chord flips it to the other side.
- Trim also works on arcs (a trimmed circle becomes an arc, which can be trimmed again).
- Objects under the cursor turn magenta in Select, Trim, Fillet and Chamfer.
- Copy / Cut ask for a base point: it is set automatically (the first part's origin, otherwise the lower-left corner) and marked in magenta; click to choose another or press Enter to keep it. Paste holds the copy by that point.
- Placing a block on a wire that has a typed/locked/ignored number: the number stays with the longer piece, the new piece is automatic.
- Wire number dialog: "Clear (no number at all)".

## 0.8.7
- Dragging a block with slots: wires attached to its slots follow. Along the wire they lengthen / shorten; sideways a short square connector keeps the wire orthogonal. A wire that ends up running through the block's slots is trimmed to them. One undo step.
- Wire numbering: page and zone come from the marked wire the count started from, so a wire that continues through a contact keeps `0204` + incident even if it runs back into another zone (02040, 02041).

## 0.9.0: reports (File > Export)
- **Wire list (CSV):** one row per numbered wire: Wire, Layer, Page, Zone, From, To, Other connections (`TAG:terminal`, ordered left to right then top to bottom), length in inches, number mode. Uses the numbers on the wires, so press Update wire numbers first.
- **Wire labels (CSV):** one row per wire end for label printing: Label, This end, Other end, Layer, Page, Zone.
- **Bill of materials (CSV):** placed parts grouped by part number + manufacturer + description (each part's own overrides count): Item, Qty, Part number, Manufacturer, Description, Block, Tags, plus one column per extra block data field. Files open directly in Excel.

## 0.9.1: real block bounds
A placed block now counts with its real extent (graphics + slots, rotated / mirrored / moved) instead of just its origin: Align, Array (polar centre), Rotate / Mirror pivot, Copy and Zoom extents use it. Copy still defaults its base point to the first part's origin.

## 0.9.2
- **Wire labels CSV** matches the label printer example: one column `LabelText`, each wire number twice (one label per end).
- **F7 / F8 / F9 / F3 toggles** (Grid, Ortho, Snap, Object snap) moved from the toolbar to the status bar, next to the X Y readout.
- **Edit block (geometry):** right-click a block in the library (Edit block (geometry)...) or a placed part (Edit block geometry...). The block opens in its own tab "Block: NAME" with its drawing and a slot mark per slot; the magenta cross is the block origin. Edit with any tool (lines, circles, move, Slot tool for new terminals). Library > Apply block edit (Ctrl+Shift+B) saves it to the library and this project; every placed copy follows. Closing the tab asks to save. Existing slots keep their order so per-part terminal names stay attached; label text is rebuilt from the block's label lines. Wires already attached to a placed part do not move when its slots move (drag the part to pull them).

## 0.10.0: cross-references and off-page connectors
- **`{xref}` label line** (Block data: "Cross-reference", also hideable per part): a coil lists the page/zone of every contact linked to it (contacts take the coil's tag with Part properties > Pick...); a contact shows where its coil is; an off-page connector lists the other connectors with the same name. Updates as parts are placed or moved, on any sheet.
- **Off-page connectors:** Library > Add off-page connector block adds a ready-made `GOTO` block (a flag on one slot, label = name + `{xref}`). Any block can be one: tick "Off-page connector" in Block data. When placed it asks for a name; connectors with the same name on different sheets are one wire.
- **Numbering across sheets:** the count carries over a connector (a wire marked on sheet 1 keeps counting on sheet 2), both ends get the same number, and a typed number on either end wins. Phase-set and global counters still run per sheet, so a connector wire there takes the first end's number and the count skips one.

## 0.10.1
- **Blocks bring their layers:** making or applying a block records the definition (colour, linetype, weight) of every layer its graphics use, saved in the library file. Placing a block, or updating from the library, adds any layer the project lacks; a layer with no stored definition (older blocks) is added as a plain default layer. To give an older block its dashed look, open it (Edit block geometry) in a project that has the layer and Apply.
- **Closing a block tab:** the close button now shows on block-edit tabs (it was being removed); Library > Close block edit tab does the same. Unsaved changes ask Save / Discard / Cancel.
