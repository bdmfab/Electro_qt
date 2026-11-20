"""Builds docs/Electro_qt_Manual.pdf:  python docs/build_manual.py   (needs: pip install reportlab)"""
import os
import sys
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether, Preformatted)
from reportlab.platypus.tableofcontents import TableOfContents

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from electro import __version__

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Electro_qt_Manual.pdf")
ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=5)
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, spaceBefore=4,
                    spaceAfter=10, textColor=colors.HexColor("#12355b"))
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, spaceBefore=10,
                    spaceAfter=4, textColor=colors.HexColor("#12355b"))
BUL = ParagraphStyle("bul", parent=BODY, leftIndent=16, bulletIndent=5, spaceAfter=2.5)
NOTE = ParagraphStyle("note", parent=BODY, backColor=colors.HexColor("#eef4fb"), borderColor=colors.HexColor("#9db8d6"),
                      borderWidth=0.6, borderPadding=5, leftIndent=6, rightIndent=6, spaceBefore=4, spaceAfter=8)
CODE = ParagraphStyle("code", parent=BODY, fontName="Courier", fontSize=8.6, leading=11, leftIndent=10,
                      backColor=colors.HexColor("#f4f4f4"), borderPadding=4, spaceAfter=8)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=9, leading=11.5, spaceAfter=0)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")

story = []


def h1(t):
    story.append(PageBreak()); story.append(Paragraph(t, H1))


def h2(t):
    story.append(Paragraph(t, H2))


def p(t):
    story.append(Paragraph(t, BODY))


def bl(*items):
    for i in items:
        story.append(Paragraph(i, BUL, bulletText="•"))
    story.append(Spacer(1, 4))


def note(t):
    story.append(Paragraph("<b>Note.</b> " + t, NOTE))


def code(t):
    story.append(Preformatted(t, CODE))


def table(rows, widths, head=True):
    data = [[Paragraph(str(c), CELLB if (head and r == 0) else CELL) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * inch for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b0b6bd")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbe6f2")))
    t.setStyle(TableStyle(st))
    story.append(t); story.append(Spacer(1, 8))


class Doc(BaseDocTemplate):
    def __init__(self, fn):
        super().__init__(fn, pagesize=letter, leftMargin=0.9 * inch, rightMargin=0.9 * inch, topMargin=0.85 * inch,
                         bottomMargin=0.8 * inch, title="Electro_qt User Manual", author="Electro_qt")
        fr = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate(id="p", frames=[fr], onPage=self.deco)])

    def deco(self, c, d):
        c.saveState(); c.setFont("Helvetica", 8); c.setFillColor(colors.HexColor("#666666"))
        c.drawString(0.9 * inch, 0.5 * inch, f"Electro_qt {__version__} - User Manual")
        c.drawRightString(letter[0] - 0.9 * inch, 0.5 * inch, f"Page {d.page}")
        c.restoreState()

    def afterFlowable(self, fl):
        if isinstance(fl, Paragraph) and fl.style.name in ("h1", "h2"):
            self.notify("TOCEntry", (0 if fl.style.name == "h1" else 1, fl.getPlainText(), self.page))


# ============================================================================================ content
def build():
    story.append(Spacer(1, 1.6 * inch))
    story.append(Paragraph("Electro_qt", ParagraphStyle("t", parent=H1, fontSize=34, leading=40, alignment=TA_LEFT)))
    story.append(Paragraph("User Manual", ParagraphStyle("t2", parent=H1, fontSize=22, leading=28)))
    story.append(Paragraph(f"Version {__version__}", BODY))
    story.append(Spacer(1, 0.3 * inch))
    p("A 2D drawing program for industrial electrical schematics and panel layouts: draw from scratch, place "
      "parts from a shared library, number the wires automatically, lay the parts out on the back plate to "
      "scale, and export PDF, DXF, wire lists, labels and a bill of materials.")
    note("This manual describes the program as built. Menu names are written like <b>Sheet &gt; Update wire "
         "numbers</b>. Keys are written in capitals (<b>F5</b>, <b>Ctrl+B</b>). There are no screenshots: "
         "every dialog is named so you can find it in the menus.")
    story.append(PageBreak())
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("t1", fontName="Helvetica-Bold", fontSize=10.5, leading=15, leftIndent=0),
                       ParagraphStyle("t2", fontName="Helvetica", fontSize=9.5, leading=12.5, leftIndent=16)]
    story.append(Paragraph("Contents", H1)); story.append(toc)

    # ------------------------------------------------------------------ 1
    h1("1. Getting started")
    h2("Install and start")
    bl("<b>Windows:</b> run <b>Electro_qt_Setup.exe</b>, or unzip the program folder anywhere and run "
       "<b>Electro_qt.exe</b>. No Python is needed.",
       "<b>Linux:</b> unpack the .tar.gz anywhere and run <b>Electro_qt</b>. If it will not start, install the "
       "Qt helper library once: <font face='Courier'>sudo apt install libxcb-cursor0</font>.",
       "<b>From source:</b> <font face='Courier'>pip install -r requirements.txt</font>, then "
       "<font face='Courier'>python run_electro.py</font>.")
    h2("Where things are kept")
    table([["What", "Where"],
           ["A job (drawings, layers, header styles, panel layouts, reference PDFs, block copies)",
            "One <b>.eqt</b> file that you save and open (File &gt; Save / Open). Everything for the job is inside it."],
           ["The shared block library", "A folder of <b>.eqblock</b> files (one per block; sub-folders are library "
            "folders). Default: <b>blocks</b> next to the program when run from source; "
            "<b>%APPDATA%\\Electro_qt\\blocks</b> (Windows) or <b>~/.local/share/Electro_qt/blocks</b> (Linux) when "
            "installed. Library &gt; Library folder... points it at a network drive to share it."],
           ["Footprint profiles", "A hidden file <b>.electro_profiles.ini</b> inside the library folder, so it "
            "travels with the library (section 9)."],
           ["Your preferences (background colour, library folder choice)", "Stored per user by the system: the "
            "registry on Windows, ~/.config on Linux. Upgrading or reinstalling does not change them."],
           ["Exports", "PDF, DXF, wire list, labels and BOM are written next to the saved .eqt file (pdf and dxf "
            "folders). Save the job first."]], [2.3, 4.4])
    h2("A first drawing")
    bl("File &gt; New gives one 11x17 sheet. Draw with the tools on the toolbar (section 3).",
       "Press <b>Ctrl+L</b> and make your layers (a wire layer for each voltage). Wires are lines on a layer "
       "marked <i>Wire layer</i>.",
       "Place parts from the Library dock, mark the start of each wire (right-click &gt; Mark wire, or <b>Q</b>), "
       "then press <b>F5</b> to number every wire.",
       "File &gt; Export gives you PDF, DXF and the reports.")

    # ------------------------------------------------------------------ 2
    h1("2. The window")
    table([["Part", "What it does"],
           ["Tabs", "One tab per sheet. Block-edit tabs ('Block: NAME'), DXF scratch tabs and reference-PDF tabs "
            "open beside them. Panel layouts are always the last sheets."],
           ["Tool toolbar", "Select, Line, Rect, Circle, Arc, Dot, Text, Trim, Fillet, Chamfer, Multiline, Slot. "
            "A tool returns to Select when it finishes."],
           ["Second toolbar", "Layers..., current layer, Standards..., Header styles..."],
           ["Panel toolbar", "Appears to the right of the tools whenever a panel layout sheet is open."],
           ["Library dock (left)", "The block library as a folder tree. Double-click a block to place it."],
           ["Properties dock (right)", "Layer, colour, line weight, radius, device tag and the Part properties "
            "button for what is selected. 'Varies' is shown for mixed values."],
           ["Panel parts dock", "The schematic's parts not yet on a panel layout (View menu)."],
           ["Status bar", "Cursor X Y and snap type; toggles for Grid (F7), Ortho (F8), Snap grid (F9), Object "
            "snap (F3); a prompt line that tells you the next step of the current tool."]], [1.6, 5.1])
    h2("Menus")
    table([["Menu", "Contents"],
           ["File", "New, Open, Open DXF (scratch tab), Open reference PDF, Save, Save As, Export, Quit"],
           ["Edit", "Copy, Cut, Paste, Delete, Select all, Make block, Explode block, Array, Rotate, Mirror"],
           ["Sheet", "Add / delete / move / renumber sheets, Letter rules, Update wire numbers (F5), Update device "
            "tags, Rule check, Title block, Sheet type, cover sheet and title-block images"],
           ["Panel", "Panel layout commands (section 9)"],
           ["View", "Zoom extents (Home), Grid divisions, Background colour, dock visibility"],
           ["Library", "Add off-page connector block, Apply block edit (Ctrl+Shift+B), Update project blocks from "
            "library, Reload library, Library folder, default library folder"],
           ["Help", "User manual (F1), About"]], [1.2, 5.5])
    note("Everywhere: <b>Esc</b> cancels, <b>Space</b> does the same as <b>Enter</b>, and a right-click on empty "
         "space repeats the last command. Right-click on an object shows the commands for it.")

    # ------------------------------------------------------------------ 3
    h1("3. Drawing")
    h2("Tools and keys")
    table([["Key", "Tool", "Notes"],
           ["V", "Select", "Click, or drag a box. Hold a click for 300 ms before dragging an object, so a click never nudges it."],
           ["L", "Line", "Click points; Esc or right-click ends. Type a length and press Enter or Space."],
           ["R / C / A", "Rectangle / Circle / Arc", "Arc: click both ends, then move the centre to set the radius."],
           ["D", "Dot", "A filled dot (a junction)."],
           ["T", "Text", "Opens the text editor (below)."],
           ["X / F / H", "Trim / Fillet / Chamfer", "Click the part of each line to keep. Fillet and chamfer take a typed value."],
           ["M", "Multiline", "Parallel wires, one layer each, from the active preset (Standards...)."],
           ["S", "Slot", "Marks where a wire lands on a part (section 5)."],
           ["Q", "Mark wire", "Marks the selected wire (or the one under the cursor) as a numbering start."]],
          [0.9, 1.6, 4.2])
    h2("Snaps, grid, view")
    bl("<b>F7</b> grid, <b>F8</b> ortho (holds a drag to one axis), <b>F9</b> grid snap, <b>F3</b> object "
       "snap. The grid sits on the row lines of the sheet; View &gt; Grid divisions sets lines between rows.",
       "Mouse wheel zooms, middle-drag pans, <b>Home</b> fits everything.",
       "Objects under the cursor turn magenta in Select, Trim, Fillet and Chamfer.")
    h2("Layers and colours")
    p("<b>Layers...</b> (Ctrl+L) holds your layers: colour, line type, line weight. Tick <i>Wire layer</i> to "
      "give the layer wire-numbering options (a scheme, and a phase for AC). Layers are made by you; blocks bring "
      "the layers they need when placed. Colour and line weight can be overridden per object in the Properties "
      "dock.")
    p("<b>Standards...</b> and <b>Multiline (M)</b>: a standard names a set of parallel wires (for example 3 "
      "phase + PE) with a layer and colour each. Pick one and draw; missing layers are offered for creation.")
    h2("Editing")
    bl("<b>Copy / Cut / Paste</b> (Ctrl+C / X / V) ask for a base point; the clipboard is shared across sheets.",
       "<b>Rotate</b> (Ctrl+R, Ctrl+Shift+R, custom angle) and <b>Mirror</b> (Ctrl+M, Ctrl+Shift+M).",
       "<b>Align</b> and <b>Distribute</b> (right-click with 2+ selected). <b>Array</b> (Ctrl+Shift+A): rows x "
       "columns or polar, optionally counting up a trailing number in text (TB09 to TB10).",
       "<b>Group</b> / Ungroup, and <b>Resize</b> of a group by its side grips.",
       "<b>Grips</b>: a selected line shows grips on every segment; dragging a middle grip moves the segment "
       "sideways and its neighbours stretch. A circle has a radius grip.",
       "Every change is undoable (Ctrl+Z) per sheet.")
    h2("Text")
    p("The Text tool and a double-click on a text open the text editor: bold, italic, underline, size, colour, "
      "<b>font</b> and justify left / centre / right per selection. Size is relative to the text height (12 pt is "
      "normal). Field codes such as <font face='Courier'>{page}</font>, <font face='Courier'>{tag}</font> and "
      "<font face='Courier'>{job}</font> work inside the text.")

    # ------------------------------------------------------------------ 4
    h1("4. Sheets and the title block")
    bl("<b>Sheet &gt; Add sheet from template...</b>: 11x17 landscape, 1 column (zones 00-24) or 2 columns "
       "(00-49), with the zone ruler and a title block (JOB, DRAWN, DATE, TITLE lines, PAGE n OF m). Pages are "
       "two digits.",
       "<b>Title block...</b> sets the job, drawn-by, date and titles; <b>Title block image...</b> puts your logo "
       "in the logo box on every sheet.",
       "<b>Sheet type</b> switches between 1 and 2 columns. <b>Move sheet...</b> and <b>Renumber sheets</b> "
       "change the order. Deleting a sheet renumbers the rest.",
       "<b>Add cover sheet</b> makes page 00 with a large title and an optional picture (movable and resizable "
       "in Select).",
       "<b>Panel layout sheets are always last</b>, even when you add more sheets later.")
    note("After you move, delete or change the type of a sheet, press <b>F5</b> (Update wire numbers) again: "
         "pages and zones feed the wire numbers and goto connector names.")

    # ------------------------------------------------------------------ 5
    h1("5. Parts: blocks and the library")
    h2("Make a block")
    bl("Draw the part. With the <b>Slot tool (S)</b> click each place a wire lands and name the terminal (names "
       "count up: 1, 2, ...). Slots are taken in pairs - 1-2, 3-4 - and each pair is one pole.",
       "Select the drawing and its slots, then <b>Edit &gt; Make block...</b> (Ctrl+B). Fill in the "
       "<b>Part properties</b> dialog: name, folder, type, tag prefix (CB, KM, FU...), poles, description, "
       "manufacturer, part number, hyperlink, label position and header style, and the footprint.",
       "Choose the block's origin: a slot, the centre, or a point you pick. That point sits on the cursor when "
       "the block is placed.")
    h2("The four types")
    table([["Type", "Meaning"],
           ["On back plate", "A part that goes on the panel: it has a footprint and appears on the layout and the BOM."],
           ["Not on back plate", "In the BOM but no footprint (a field device, for example)."],
           ["Off-page connector", "A From / To flag that joins wires across sheets (section 6)."],
           ["Exclude from BOM", "Drawn but left out of the bill of materials."]], [1.6, 5.1])
    p("The type belongs to the <b>block</b>. Every placed copy shares it. Description, part number, "
      "manufacturer, tag and terminal names can differ <b>per placed part</b> (double-click it).")
    h2("The library")
    bl("The Library dock is a folder tree of the shared library. <b>Double-click</b> a block to place it; "
       "<b>Ctrl+R / Ctrl+M</b> turn and flip the ghost before you click. Wires that run through the block's slots "
       "are trimmed to them, and wires attached to a block follow when you drag it.",
       "Placing copies the block into the job, so a job still opens without the library. Right-click a library "
       "block for Data, Copy (rename), Delete, Edit block (geometry), Import / Export (.eqlib), and folder "
       "commands.",
       "<b>Library &gt; Update project blocks from library...</b> replaces the job's copies with the library "
       "versions. <b>Reload library</b> re-reads the folder. Files that cannot be read are listed and never "
       "deleted.",
       "<b>Edit block geometry</b> opens a block in its own tab (the magenta cross is its origin). Change it with "
       "any tool, then <b>Library &gt; Apply block edit</b> (Ctrl+Shift+B): the library and every placed copy "
       "follow. <b>Explode block</b> turns a placed part into plain objects you can edit.")
    h2("Placed parts")
    bl("<b>Double-click a placed part</b> (or Properties &gt; Part properties...) to edit that one part: "
       "description, part number, manufacturer, tag, which label lines show, terminal names and its footprint "
       "profile.",
       "<b>Device tags</b> are prefix + page + zone (CB0111 is page 01, zone 11), with A, B, ... added if another "
       "automatic tag has the same zone. <b>Sheet &gt; Update device tags...</b> recomputes the automatic ones "
       "and renames the matching parts on the panel layout. A tag you type is manual and is never changed; "
       "clearing the tag, or typing just the prefix (PS), makes it automatic again.",
       "<b>Pick...</b> next to the tag makes a part take another part's tag (a contact takes its coil's), and it "
       "follows when tags update.",
       "The <b>{xref}</b> label line shows where a coil's contacts are (and where a contact's coil is), as page/zone.")
    h2("Labels and header styles")
    p("The text beside a part is its <b>label</b>: description, part number, tag, cross-reference. In Part "
      "properties choose which lines show and the <b>Label position</b> (above, right, inside, in a corner). "
      "A <b>Header style</b> controls how it looks (section 7).")
    h2("Bringing in DXF drawings")
    p("<b>File &gt; Open DXF (scratch tab)...</b> reads an ASCII DXF into its own tab (units are asked and "
      "converted to inches). It is a workbench: copy objects into any sheet with a base point, or Make block from "
      "a selection. The drawing's own blocks come across as project blocks; a WIRE# attribute inside one becomes "
      "a slot. Splines, hatches, solids, dimensions, leaders, images and 3D objects are skipped and listed. "
      "The tab is not saved with the job.")

    # ------------------------------------------------------------------ 6
    h1("6. Wire numbering")
    h2("The idea")
    p("Wires are lines on wire layers. One <b>wire</b> is every line on the same layer that touches end to "
      "end, ends on the side of another, or meets at a dot. A plain crossing is not a connection (the more "
      "vertical wire hops over); a solid dot connects. Blocks separate wires. Right-click a crossing to choose "
      "<i>Connect wires here (dot)</i> or <i>Hop</i>.")
    h2("Mark, then update")
    bl("<b>Mark wire</b> (right-click, or <b>Q</b>) sets where counting starts and its start number. An orange "
       "diamond shows it.",
       "<b>Sheet &gt; Update wire numbers</b> (<b>F5</b>) numbers every wire reachable from a mark, on all "
       "sheets. Numbers print beside the middle of each wire; orange means override or locked.",
       "Each number is built from the layer's <b>scheme</b>: &lt;page&gt;&lt;zone&gt;&lt;incident&gt; for DC, "
       "&lt;phase_incident&gt;&lt;L|T&gt;&lt;phase&gt; for AC (1L1 1L2 1L3, then 2L1...), or a global counter. "
       "Choose or build a scheme in the Layers dialog.",
       "The <b>zone</b> comes from the marked wire's left (or top) end, so mark the wire where you want its "
       "zone taken from.",
       "An <i>incrementing</i> block (Part properties &gt; Increment) adds 1 to the count for each pole passed. "
       "<b>Letter rules</b> (Sheet menu) turn L into T after a motor, for example.")
    h2("Typed numbers")
    p("Right-click &gt; <b>Wire number...</b>: Automatic, Override (your number, the sequence continues), "
      "Locked (never changed), Clear (none at all), or Goto. Update never changes an override or locked "
      "number. If wires have typed numbers after a sheet moves, Update offers to switch them back to automatic.")
    h2("Going to another sheet: From and To")
    bl("<b>Library &gt; Add off-page connector block</b> adds a <b>From</b> (shows the cross-reference) and a "
       "<b>To</b>, in a folder GOTO. Place one at each end of a wire and give both the same name.",
       "Wires tied by a connector are one wire: the To wire takes the From wire's number.",
       "When Update finds the same number on two wires it offers to apply a goto: a From and To named "
       "NUMBER-1 (then NUMBER-2...) are placed on free ends automatically. <b>Wire number... &gt; Goto</b> does "
       "it for one pair.")
    h2("Warnings and Rule check")
    p("Update lists wires no mark reaches, duplicate numbers, two routes giving different numbers, and "
      "incidents above 9. <b>Sheet &gt; Rule check...</b> lists probable mistakes without changing anything: "
      "duplicate tags, parts with no tag, slots with no wire, unreached wires, broken tag links, and "
      "off-page connectors that appear once. Double-click a line to jump to it; Export CSV saves the list.")

    # ------------------------------------------------------------------ 7
    h1("7. Header styles")
    p("A <b>header style</b> says how a part's label text looks. Define styles once for the job and let each "
      "block pick one, so you never edit text part by part.")
    h2("Make a style")
    bl("Click <b>Header styles...</b> on the second toolbar. New, Rename, Copy and Delete manage the list "
       "(at least one style must remain).",
       "<b>Edit text, sizes and colours...</b> opens the text editor. Type the header as it should read, one line "
       "per field:",)
    code("{DESC}\n{PART}\n{LOC}\n{XREF}")
    table([["Variable", "Shows"],
           ["{DESC}", "the part's description"],
           ["{PART}", "the part number (or {PART#})"],
           ["{LOC}", "the tag, which encodes the location (page and zone); {TAG} is the same"],
           ["{XREF}", "the cross-reference (where its coil or contacts are)"]], [1.4, 5.3])
    bl("Select a variable and give it its own <b>size, colour and font</b> in the editor. Size is a multiple of "
       "the normal 0.1 in text height (12 pt is normal). Example: DESC at 16 pt in colour 3, PART at 14 pt in "
       "colour 4, LOC at 10 pt.",
       "<b>Justify</b>: Automatic suits the label position (centred above the part, left beside it); or force "
       "left / centre / right.",
       "<b>Line spacing</b>: a multiple of normal.",
       "<b>Distance from part</b> (inches, default 0.1): how far the text sits from the part - from its top for "
       "labels above, from its side for labels to the right, from the corner for corner labels. A smaller "
       "value suits styles with small text on small parts. A negative value pulls the text onto the part, so "
       "try small steps (-0.02 to -0.05).")
    h2("Use a style")
    bl("In <b>Part properties</b> (double-click a part, or Make block) choose the <b>Header style</b> next to "
       "Label position. 'None' keeps separate plain lines. The block's label position still decides where "
       "the header sits.",
       "A line whose variables are all empty (or switched off with the Show boxes in Part properties) "
       "<b>drops out</b> and the header closes up. Fixed text typed in the style stays.",
       "Drag the label grip of one placed part to nudge just that part; right-click &gt; <b>Reset label "
       "position</b> puts it back.")
    note("Header styles are saved in the job. A library block that names a style the job does not have uses the "
         "job's first style. Renaming a style updates the blocks that use it. In a DXF export a header becomes "
         "one attribute, HEADER, holding the plain text.")

    # ------------------------------------------------------------------ 8
    h1("8. Reports and export")
    p("Save the job first: exports go next to the .eqt file. Every export ends with a window listing the "
      "files written, with an Open folder button. Press <b>F5</b> before the wire reports so they use current "
      "numbers.")
    table([["Export", "Result"],
           ["Wire list (CSV)", "One row per numbered wire: wire, layer, page, zone, from, to, other connections, "
            "length (in), number mode."],
           ["Wire labels (CSV)", "One column, LabelText: each wire number twice (one label per end), for a label printer."],
           ["Bill of materials (CSV)", "Placed parts grouped by part number + manufacturer + description: item, "
            "qty, part number, manufacturer, description, block, tags, plus one column per extra block data field. "
            "Terminal blocks on a panel layout are added, grouped by part number. Off-page connectors and "
            "excluded parts are left out; the window warns about blank part numbers."],
           ["PDF - all sheets", "<b>pdf/&lt;tab name&gt;.pdf</b> per sheet and one merged <b>pdf/&lt;Job&gt;.pdf</b>. "
            "Vector, black on white. Reference PDFs are appended to the merged file."],
           ["PDF - this sheet", "Just the current sheet."],
           ["DXF", "<b>dxf/&lt;tab name&gt;.dxf</b> per sheet: parts as real blocks with attributes (TAG, "
            "DESCRIPTION, PART_NUMBER, MANUFACTURER, XREF, TERM1..n, HEADER), layers keep colour, line type and "
            "weight, wire numbers on layer WIRE_NUMBERS. Reference PDFs are ignored. Needs ezdxf."]], [1.7, 5.0])
    h2("Reference PDFs")
    p("<b>File &gt; Open reference PDF...</b> embeds a datasheet or standard in the job and shows it in its own "
      "tab, for looking things up while you draw. It is saved inside the .eqt file and added to the merged PDF "
      "export; it is ignored by DXF. Closing the tab removes it from the job.")

    # ------------------------------------------------------------------ 9
    h1("9. Panel layouts")
    p("A panel layout is a sheet drawn <b>1:1</b> in front view: the back plate, DIN rails, wire duct, and "
      "each part's footprint. Panel layouts are always the last sheets.")
    h2("Set up")
    bl("<b>Panel &gt; New panel layout...</b>: type the back plate size (inches or mm), or take it from a block "
       "that has a footprint. Add more layouts later and they follow the last layout.",
       "<b>Insert DIN rail / wire duct...</b>: pick a size, click to drop a 1 in piece, press <b>Space</b> to turn "
       "it, then drag its yellow end handles to the length you want. <b>Size of selected...</b> types exact "
       "sizes.",
       "<b>Place a part...</b> (or double-click one in the Panel parts dock): the schematic's parts not yet on a "
       "layout. Parts without a footprint are greyed. A part that mounts on a DIN rail snaps its rail centre "
       "line onto the rail and turns to follow it (<b>Space</b> flips it 180 degrees).",
       "Snapping: edges and centres of other objects (a pink guide shows), plus an optional <b>Spacing between "
       "objects</b> gap. Block edges snap to each other.",
       "<b>Check layout</b> lists overlaps, parts off the plate, and rail parts not on a rail.")
    h2("Footprints and profiles")
    p("The schematic keeps one generic block (a breaker, a contactor, a fuse holder); the layout differs "
      "per part. In Part properties each placed part has a <b>Panel footprint</b>: width, height, depth, "
      "mounting (DIN rail or back plate) and the rail centre line. Paste the manufacturer, part number and "
      "hyperlink and, if that part number is a known <b>profile</b>, the footprint fills in; change a value to "
      "overwrite it. A new part number is saved as a new profile when you press OK. The profile list shows only "
      "profiles for that block. Profiles live in the hidden readable file <b>.electro_profiles.ini</b> in the "
      "library folder:")
    code("[Siemens 3RT2015-1BB41]\nblock = 3ph Contactor\nmanufacturer = Siemens\npart_number = 3RT2015-1BB41\n"
         "hyperlink = https://...\nwidth = 1.77\nheight = 3.34\ndepth = 3.46\nmounting = rail\nrail_cl = 0.0\nunits = in")
    h2("Terminal blocks")
    bl("<b>Panel &gt; Add terminal blocks...</b>: pick a block from <b>Library/Terminals</b> and a quantity "
       "(default 1). The identifier comes from the block's tag prefix and counts up (TB1, TB2...). The stack "
       "goes down as one group; Space turns it; right-click &gt; <b>Ungroup terminal blocks</b> splits it.",
       "<b>Label the terminals</b>: double-click a stack. Terminals are named TB1.1, TB1.2... Change the "
       "identifier or first number to renumber all, or edit one label to override it. The quantity can be "
       "changed here too.",
       "<b>Label from wire numbers...</b> lists every wire number that ends at a connection dot, as "
       "<b>01131 x 8</b> (how many dots are not yet given to a terminal; counts include terminals on every "
       "layout). Select the first terminal to label, then double-click a number to use it for that terminal, or "
       "right-click &gt; <b>Apply to multiple...</b> to label several in a row (the count defaults to what is "
       "left). If there are not enough terminals you are asked whether to add the rest. Labelling can overwrite. "
       "Press Update wire numbers (F5) first so the list is current.",
       "Every terminal, labelled or not, appears in the BOM. Right-click &gt; Exclude from BOM leaves a stack out.")
    h2("Dimensions")
    bl("<b>Panel &gt; Dimension</b>: click two points, then click where the line goes. Horizontal or "
       "vertical only; Space switches. Dimension text shows one decimal for inches and none for millimetres "
       "(Panel &gt; Dimension units). Text height: right-click &gt; Dimension text height...",
       "<b>Attached ends:</b> an end that sits on an object's edge or centre attaches to it. Moving, resizing or "
       "rotating that object updates the dimension; dragging a dimension point free of its object detaches it.",
       "<b>Change the value:</b> double-click a dimension, or right-click &gt; Dimension value..., and type "
       "it. If neither object is locked, both move, half each. If one is locked, the other moves the whole way. "
       "If both are locked it is refused.",
       "<b>Move an object:</b> an unlocked object dimensioned to it follows along the dimension's direction so "
       "the distance holds. The chain continues through further dimensions and stops at locked objects (that "
       "dimension then simply changes).")
    h2("Lock")
    p("Select any layout object and press <b>L</b> (or right-click &gt; Lock) to lock it: it cannot be moved, "
      "turned or resized, and no dimension moves it. A small ring marks it. Lock the back plate to keep it fixed "
      "while parts are dimensioned to it.")
    h2("Output")
    p("Panel layouts print to PDF on an 11x17 landscape page with a border and title block (the layout "
      "scaled uniformly, the drawing itself stays 1:1) and export to DXF at 1:1 in inches. Extra layouts are "
      "extra pages.")

    # ------------------------------------------------------------------ 10
    h1("10. Files, sharing and troubleshooting")
    h2("Sharing a library between machines")
    p("Put the <b>blocks</b> folder on a shared drive and, on each machine, choose <b>Library &gt; Library "
      "folder...</b>. Footprint profiles are in the same folder, so they are shared too. Each machine remembers "
      "its own choice. Jobs carry copies of the blocks they use, so they open anywhere.")
    h2("Backing up")
    bl("Back up your .eqt jobs and the library folder. That is everything.",
       "To move to a new machine, install the program, copy the library folder and choose it with Library &gt; "
       "Library folder...")
    h2("Common questions")
    table([["Problem", "What to check"],
           ["A tag stays as PS and will not update", "It is flagged manual. Open Part properties, clear the tag or "
            "type just the prefix, press OK, then Sheet > Update device tags."],
           ["No wire numbers appear", "Mark a wire (Q) on each run and press F5. Wires on a layer not marked 'Wire "
            "layer' are never numbered."],
           ["The same wire number appears twice", "Two runs were reached from different marks, or one is typed. "
            "Press F5: it offers to apply a goto for true duplicates."],
           ["Terminal label list is empty", "Press F5 first. The list is built from the numbers already assigned and "
            "uses the automatic junction dots and dots placed with the Dot tool."],
           ["Panel layout text did not follow a new tag", "Press Sheet > Update device tags once; layouts follow it."],
           ["A block's text looks too far from a small part", "Lower <b>Distance from part</b> in its header style."],
           ["PDF or DXF folder is missing", "Save the job first: exports go next to the .eqt file."],
           ["DXF export does nothing", "ezdxf is needed (it is bundled in installed builds)."],
           ["Linux: the program will not start", "sudo apt install libxcb-cursor0"]], [2.3, 4.4])

    # ------------------------------------------------------------------ 11
    h1("11. Quick reference")
    table([["Key", "Action"],
           ["V L R C A D T", "Select, Line, Rect, Circle, Arc, Dot, Text"],
           ["X F H", "Trim, Fillet, Chamfer"],
           ["M / S", "Multiline / Slot"],
           ["Q", "Mark the wire (numbering start)"],
           ["F5", "Update wire numbers"],
           ["F7 F8 F9 F3", "Grid, Ortho, Snap grid, Object snap"],
           ["F1", "This manual"],
           ["Home", "Zoom to fit"],
           ["Space / Enter / Esc", "Accept / accept / cancel; Space also turns the part or panel object being placed"],
           ["Right-click on blank space", "Repeat the last command"],
           ["Ctrl+Z / Ctrl+Y", "Undo / redo (redo is Ctrl+Shift+Z on Linux)"],
           ["Ctrl+C X V", "Copy, Cut, Paste"],
           ["Ctrl+R  Ctrl+Shift+R", "Rotate 90 counter-clockwise / clockwise"],
           ["Ctrl+M  Ctrl+Shift+M", "Mirror left-right / top-bottom"],
           ["Ctrl+B", "Make block"],
           ["Ctrl+Shift+X", "Explode block"],
           ["Ctrl+Shift+A", "Array"],
           ["Ctrl+Shift+B", "Apply block edit"],
           ["Ctrl+L", "Layers"],
           ["L (panel layout)", "Lock / unlock the selected object"],
           ["Del", "Delete"]], [2.0, 4.7])
    h2("Field codes")
    table([["Code", "Value"],
           ["{tag}  {description}  {part}  {manufacturer}", "Of the placed part"],
           ["{xref}", "Cross-reference of the placed part"],
           ["{page}  {pages}  {job}  {drawn}  {date}", "Title block fields (usable in any text)"]], [3.2, 3.5])


def make(path=OUT):
    story.clear()
    build()
    Doc(path).multiBuild(story)
    return path


if __name__ == "__main__":
    print(make())
