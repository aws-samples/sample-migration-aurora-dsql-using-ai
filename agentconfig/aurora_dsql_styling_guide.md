# Aurora DSQL Report Styling Guide

## MANDATORY PRE-GENERATION CHECKLIST 

**BEFORE GENERATING ANY HTML REPORT, YOU MUST EXPLICITLY CONFIRM:**

- [ ] **COMPLETE EMBEDDED SQL**: Will embed 100% complete DDL for ALL tables (every single table, no samples, no "...", no placeholders)
- [ ] **COMPLETE EMBEDDED SQL - INDEXES**: Will embed 100% complete CREATE INDEX statements for ALL indexes
- [ ] **COMPLETE EMBEDDED SQL - ALL OBJECTS**: Will embed ALL views, functions, and documentation for removed objects
- [ ] **ALL TABLES TAB**: Will list EVERY table in the All Tables tab (no "+X additional tables" rows)
- [ ] **EXPAND ALL BUTTONS**: Will add "Expand All" buttons to both Critical Issues tab AND Compatible Tables tab
- [ ] **CORRECT DISPLAY LOGIC**: Will use `display: none/block` for collapsible content (NOT max-height transitions)
- [ ] **NO COLORED BACKGROUNDS**: Compatibility and recommendation boxes have NO background colors or borders
- [ ] **CORRECT COUNTS**: Executive summary table counts match actual number of tables listed
- [ ] **NO SUMMARY ROWS**: Zero instances of "+X additional" or "remaining tables" text anywhere
- [ ] **COMPLETE DDL IN COLLAPSIBLES**: Every collapsible section shows actual full DDL, not placeholders

**IF YOU CANNOT CONFIRM ALL ITEMS ABOVE, DO NOT GENERATE THE REPORT. ASK FOR CLARIFICATION FIRST.**

---

## AI-GENERATED OUTPUT DISCLAIMER 

**MANDATORY: Every HTML report MUST include this disclaimer prominently at the top (after the title, before executive summary):**

```html
<div class="ai-disclaimer" style="background: #fff3cd; border-left: 5px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 5px;">
    <h3 style="margin-top: 0; color: #856404;">⚠️ AI-Generated Analysis Disclaimer</h3>
    <p style="margin-bottom: 0; color: #856404;">
        This migration analysis report was generated using AI-powered tools. While the analysis aims to identify compatibility issues and provide recommendations, it should be thoroughly reviewed and validated by database administrators and developers familiar with your specific use case. Always test the converted schema and validate data integrity in a non-production environment before applying changes to production systems. AWS does not guarantee the accuracy or completeness of AI-generated recommendations.
    </p>
</div>
```

**Placement:** Insert immediately after the `<h1>` title and metadata box, before the Executive Summary section.

---

## Overview
This styling guide defines the HTML/CSS template structure for generating Aurora DSQL migration analysis reports. The design emphasizes compactness and space efficiency for handling large database schemas.

## Color Palette
- **Primary Dark**: `#232F3E` (AWS dark blue)
- **Primary Accent**: `#FF9900` (AWS orange)
- **Background**: `#f5f5f5` (light gray)
- **White**: `#ffffff`
- **Text**: `#333333`

### Severity Colors
- **Critical**: `#dc3545` (red)
- **High**: `#fd7e14` (orange)
- **Medium**: `#ffc107` (yellow)
- **Low/Supported**: `#28a745` (green)
- **Info**: `#17a2b8` (cyan)

## CSS Classes

### Layout
- `.container` - Main content wrapper (max-width: 1400px, white background, shadow, padding: 20px)

### Typography (Compact Sizing)
- `h1` - Main title (color: #232F3E, bottom border: #FF9900, 1.6em, padding-bottom: 6px, margin-bottom: 12px)
- `h2` - Section headers (white text, #232F3E background, 1.3em, padding: 8px 15px, margin: 20px 0 12px 0)
- `h3` - Subsection headers (#232F3E, bottom border, 1.1em, padding-bottom: 5px, margin: 12px 0 8px 0)
- `h4` - Minor headers (#232F3E, 1em, margin: 10px 0 6px 0)

### Components

#### Metadata Box
```css
.metadata {
    background: #f8f9fa;
    padding: 10px;
    border-left: 5px solid #FF9900;
    margin-bottom: 12px;
    border-radius: 5px;
}
```

#### Collapsible Sections (for Tables)
```css
.collapsible {
    background: #232F3E;
    color: white;
    cursor: pointer;
    padding: 6px 12px;
    width: 100%;
    border: none;
    text-align: left;
    outline: none;
    font-size: 0.95em;
    font-weight: bold;
    margin: 8px 0 0 0;
    border-radius: 5px;
    transition: background 0.3s;
}
.collapsible:hover {
    background: #FF9900;
}
.collapsible:after {
    content: '\25BC';
    float: right;
    margin-left: 10px;
    font-size: 0.8em;
}
.collapsible.active:after {
    content: '\25B2';
}
.collapsible-content {
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.3s ease-out;
}
.collapsible-content.active {
    max-height: none;
}
.toggle-all-btn {
    background: #FF9900;
    color: white;
    padding: 10px 20px;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    font-size: 1em;
    font-weight: bold;
    margin: 10px 0 20px 0;
    transition: background 0.3s;
}
.toggle-all-btn:hover {
    background: #232F3E;
}
```

#### Severity Badges
```css
.severity-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 0.85em;
    font-weight: bold;
    color: white;
}
.severity-critical { background: #dc3545; }
.severity-high { background: #fd7e14; }
.severity-medium { background: #ffc107; color: #333; }
.severity-low { background: #28a745; }
```

#### Object Card
```css
.object-card {
    background: white;
    border-left: 5px solid #FF9900;
    padding: 8px;
    margin: 8px 0;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
```

#### Compatibility Boxes
```css
.compatibility {
    padding: 8px;
    margin: 8px 0;
    border-radius: 5px;
}
.compatibility.critical { }
.compatibility.medium { }
.compatibility.supported { }
```

#### Recommendations Box
```css
.recommendations {
    padding: 8px;
    margin: 8px 0;
    border-radius: 5px;
}
```

#### Summary Box
```css
.summary-box {
    background: white;
    color: #333;
    padding: 12px;
    border-radius: 10px;
    margin: 12px 0;
    border: 1px solid #ddd;
}
```

#### DDL Code Block
```css
.ddl-block {
    background: #2d2d2d;
    color: #f8f8f2;
    padding: 8px;
    border-radius: 5px;
    overflow-x: auto;
    margin: 8px 0;
    font-family: 'Courier New', monospace;
    font-size: 0.75em;
    line-height: 1.3;
    white-space: pre;
}
```

#### Inline Code
```css
code {
    background: #f4f4f4;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: 'Courier New', monospace;
    color: #c7254e;
}
```

#### Table of Contents
```css
.toc {
    background: #f8f9fa;
    padding: 12px;
    border-radius: 8px;
    margin: 12px 0;
}
.toc a {
    color: #232F3E;
    text-decoration: none;
    font-weight: 500;
}
.toc a:hover {
    color: #FF9900;
    text-decoration: underline;
}
```

#### Tables
```css
table {
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
}
th {
    background: #232f3e;
    color: white;
    font-weight: bold;
    padding: 12px;
}
td {
    padding: 12px;
    border: 1px solid #ddd;
}
tr:nth-child(even) {
    background: #f9f9f9;
}
```

#### Lists
```css
ul, ol {
    margin-left: 20px;
}
li {
    margin: 4px 0;
}
```

## Content Structure

### 1. Executive Summary
Use `.summary-box` with introductory paragraph followed by a table showing object types, counts, status badges, and key issues. Include migration complexity, estimated effort, and risk level at the bottom.

### 2. Table of Contents
Use `.toc` with anchor links to all major sections.

### 3. Tables Analysis Section (Tab-Based Structure)

For tables analysis, use a tab-based structure with three views:

#### Tab Structure CSS
```css
.filter-buttons { margin: 10px 0; }
.filter-btn { 
    background: #232F3E; 
    color: white; 
    padding: 8px 15px; 
    border: none; 
    border-radius: 5px; 
    cursor: pointer; 
    margin-right: 5px; 
    font-size: 0.9em; 
}
.filter-btn:hover { background: #FF9900; }
.filter-btn.active { background: #FF9900; }
.tab-content { display: none; }
.tab-content.active { display: block; }
.collapsible-content { display: none; overflow: hidden; }
.collapsible-content.active { display: block; }
```

#### Tab 1: All Tables (Comprehensive Table View)
Show all tables in a single table with three columns: Table Name, Compatibility Analysis, Recommendations.
- List ALL tables (critical + compatible) in table format
- Use severity badges in table name column
- Include compatibility analysis and recommendations in respective columns

#### Tab 2: Critical Issues (Detailed Collapsible View)
Show only tables with compatibility issues using collapsible sections with full DDL.
- Add "Expand All" button at the top
- Use collapsible sections for each critical table
- Include: Original DDL, Compatibility Analysis, Recommendations, Converted DDL
- Use object-card wrapper for content

#### Tab 3: Compatible Tables (Converted DDL)
Show all compatible tables with their converted DDL using collapsible sections.
- Add "Expand All" button at the top
- Use collapsible sections for each compatible table
- Include only Converted DDL (no compatibility analysis needed)
- Add descriptive text explaining these tables only require UUID migration

#### JavaScript for Tab Switching
```javascript
// Tab switching
function showTab(tabName) {
    var tabs = document.getElementsByClassName('tab-content');
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].classList.remove('active');
    }
    
    var btns = document.getElementsByClassName('filter-btn');
    for (var i = 0; i < btns.length; i++) {
        btns[i].classList.remove('active');
    }
    
    document.getElementById('tab-' + tabName).classList.add('active');
    event.target.classList.add('active');
}

// Toggle all in current tab
function toggleAllInTab() {
    var activeTab = document.querySelector('.tab-content.active');
    var collInTab = activeTab.getElementsByClassName('collapsible');
    var btn = event.target;
    var allExpanded = false;
    
    for (var i = 0; i < collInTab.length; i++) {
        if (collInTab[i].classList.contains('active')) {
            allExpanded = true;
            break;
        }
    }
    
    for (var i = 0; i < collInTab.length; i++) {
        var content = collInTab[i].nextElementSibling;
        if (allExpanded) {
            collInTab[i].classList.remove('active');
            content.classList.remove('active');
            btn.textContent = "Expand All";
        } else {
            collInTab[i].classList.add('active');
            content.classList.add('active');
            btn.textContent = "Collapse All";
        }
    }
}
```

#### Key Guidelines for Table Analysis Section:
1. **All Tables Tab**: Use comprehensive table format - list ALL tables (critical + compatible) with analysis and recommendations in table columns
2. **Critical Issues Tab**: Use collapsible sections with full DDL (Original + Converted) for tables with data type issues only
   - Add "Expand All" button at the top
3. **Compatible Tab**: Use collapsible sections with converted DDL for all compatible tables (no data type issues, only sequence migration)
   - Add "Expand All" button at the top
4. **No Summary Rows**: Do not include summary rows like "+X additional tables" - list every table explicitly
5. **Severity Badges**: Use only in table names, not as separate issue tags in headers
6. **Collapsible Display**: Use `display: none/block` instead of `max-height` transitions for proper visibility
7. **Button Toggle**: The "Expand All" button should change to "Collapse All" when tables are expanded

### 4. Converted DDL Section

Provide a download button for the complete converted schema with embedded SQL.

#### Structure Guidelines:
- Single download button for complete converted schema
- Summary box describing file contents
- List what's included (number of tables, types of conversions, etc.)

#### JavaScript for Download (Embedded SQL)
Embed the complete converted SQL schema directly in the HTML as a JavaScript template literal:

```javascript
<script>
    // SQL content embedded in HTML for download
    const sqlContent = `-- Aurora DSQL Compatible Schema
-- Generated: {date}
-- Database: {database_name}
-- Session ID: {session_id}
-- Total Tables: {count}

{complete_converted_ddl_for_all_tables}
`;

    // Download SQL function
    function downloadSQL() {
        const blob = new Blob([sqlContent], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'database_name_converted_schema.sql';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }
    
    // ... rest of JavaScript functions
</script>
```

#### Key Guidelines for Converted DDL Section:
1. **Single Download Button**: Provide one button to download the complete converted schema
2. **Embedded SQL**: Embed the entire converted DDL in the HTML as a JavaScript string (no external SQL file needed)
3. **Self-Contained**: The HTML file should be fully self-contained with all DDL embedded
4. **File Generation**: Use JavaScript Blob API to generate the SQL file on-the-fly when user clicks download
5. **No Sample Code**: Do not include sample conversion examples - users can view full DDL in the tabs or download the complete file
6. **Clear Description**: List what's included in the downloadable file (number of tables, types of conversions, etc.)
7. **CRITICAL - ALL TABLES REQUIRED**: The embedded SQL MUST include complete converted DDL for ALL tables (100% of tables), not just samples or examples. Every single table must have its full CREATE TABLE statement with all columns and conversions. Never use placeholders like "... (remaining tables)" or "sample shown" - generate and embed the complete DDL for every table in the database.
8. **CRITICAL - ALL DATABASE OBJECTS REQUIRED**: Beyond tables, the embedded SQL MUST also include:
   - ALL indexes with complete CREATE INDEX ASYNC statements
   - ALL views with complete CREATE VIEW statements (if any)
   - ALL compatible functions with complete CREATE FUNCTION statements (if any)
   - Documentation for removed/unsupported objects (sequences, triggers, unsupported functions)
   - Never use "... (remaining indexes)" or similar placeholders for any object type

### 5. Other Object Analysis Sections
For non-table sections (indexes, sequences, functions, etc.), use standard `.object-card` without collapsible wrappers.

Use severity badges:
```html
<span class="severity-badge severity-critical">CRITICAL</span>
<span class="severity-badge severity-high">HIGH</span>
<span class="severity-badge severity-medium">MEDIUM</span>
<span class="severity-badge severity-low">SUPPORTED</span>
```

### 6. Migration Issues Section
List all critical issues with severity badges and resolution steps.

### 7. Migration Checklist
Use checkboxes and organized lists:
```html
<ul>
    <li>☐ Task description</li>
    <li>☑ Completed task</li>
</ul>
```

### 8. Compliant Schema
Show final Aurora DSQL-compatible DDL in `.ddl-block` sections.

### 9. Summary & Next Steps
Use `.summary-box` with action items and timeline.

## Icons
Use icons for visual hierarchy in content body only (NOT in headers):
- ✅ Checklist items and success indicators
- ❌ Unsupported features and errors
- ⚠️ Warnings in content
- 💡 Recommendations

**IMPORTANT: Do NOT use icons in h1, h2, h3, or h4 headers. Headers should be text only.**

## HTML Report Generation Rules

### CRITICAL: Complete Data Inclusion

**NEVER skip, truncate, summarize, or omit any database objects when generating HTML reports from agent analysis.**

**MANDATORY: Complete Embedded SQL**
- The embedded SQL in the download section MUST contain complete converted DDL for ALL database objects (100% of all objects)
- NEVER use placeholders like "... (remaining tables)", "... (remaining indexes)", "sample shown", or "etc."
- Generate and embed the full DDL for EVERY database object:
  - ALL tables: Complete CREATE TABLE statements with all columns
  - ALL indexes: Complete CREATE INDEX statements with ASYNC syntax
  - ALL views: Complete CREATE VIEW statements (if any)
  - ALL functions: Complete CREATE FUNCTION statements (if any and compatible)
  - ALL sequences: Document removal or conversion approach
  - ALL constraints: Include in table definitions or separate ALTER TABLE statements
- This is non-negotiable - incomplete embedded SQL makes the report unusable for migration

### MANDATORY CHECKLIST - Verify Before Delivering Report:

- [ ] **All Tables Tab**: Lists ALL tables in single table format (no "+X additional" rows)
- [ ] **Critical Tab**: Has "Expand All" button + all critical tables with Original DDL + Converted DDL
- [ ] **Compatible Tab**: Has "Expand All" button + all compatible tables with Converted DDL
- [ ] **Embedded SQL - Tables**: Contains complete CREATE TABLE statements for 100% of all tables (no samples, no placeholders)
- [ ] **Embedded SQL - Indexes**: Contains complete CREATE INDEX ASYNC statements for 100% of all indexes
- [ ] **Embedded SQL - Other Objects**: Contains all views, functions, and documentation for removed objects
- [ ] **No Summary Rows**: Zero instances of "+X additional tables" or similar text
- [ ] **No Colored Backgrounds**: Compatibility/recommendation boxes have no backgrounds or borders
- [ ] **Correct Counts**: Executive summary matches actual table counts (critical vs compatible)
- [ ] **Complete DDL**: Every collapsible section shows actual DDL, not placeholders

## Best Practices

1. **Consistency**: Use the same class for similar content types
2. **Hierarchy**: Maintain clear visual hierarchy with headers and spacing
3. **Readability**: Use compact padding (8-12px) and margins for space efficiency
4. **Code Blocks**: Always use `.ddl-block` for SQL DDL statements
5. **Severity**: Apply appropriate severity badges to all issues
6. **Navigation**: Include anchor links in TOC for easy navigation
7. **Contrast**: Ensure text is readable against backgrounds
8. **Responsive**: Template is responsive with max-width container
9. **Collapsible Tables**: Use collapsible sections for table analysis to handle tables efficiently
10. **JavaScript**: Include toggle functionality for collapsible sections and "Expand All" button
