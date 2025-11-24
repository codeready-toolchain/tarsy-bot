# Documentation Update for New Features

## Context
When new features are implemented, documentation must be updated to reflect the changes. Documentation serves as the primary reference for understanding the system architecture, capabilities, and usage patterns.

## Documentation Structure

TARSy documentation follows a three-tier structure:

1. **README.md** - Brief overview, quick start, key features (high-level only)
2. **docs/architecture-overview.md** - High-level architecture concepts, design principles, and system flow
3. **docs/functional-areas-design.md** - Detailed technical implementation, component interactions, and API specifications

## Critical Rules

### 1. Ignore EP-xxxx Documents
**NEVER update EP-xxxx enhancement proposal documents** - they are historical specifications and should remain unchanged:

### 2. Update Only Relevant Documentation
**Focus on what changed:**
- ✅ Update sections that describe the new feature or modified behavior
- ✅ Update architecture diagrams if the system flow changed
- ✅ Update API endpoints if new endpoints were added
- ❌ Don't rewrite entire sections unnecessarily
- ❌ Don't add redundant information already covered elsewhere

### 3. Maintain Documentation Style and Level
**Match existing documentation style:**
- **README.md**: Brief, user-focused, highlights key capabilities
- **architecture-overview.md**: Conceptual, high-level, explains "what" and "why"
- **functional-areas-design.md**: Technical, detailed, explains "how" with code examples

**Consistency is critical:**
- Use the same terminology across all documents
- Follow existing section structure and formatting
- Match the level of detail in similar sections
- Use the same code example style and format

**Note**: If not sure then ask.

## Systematic Approach to Documentation Updates

### Step 1: Understand the New Feature

Before updating documentation:
- **Read the implementation** to understand what was built
- **Identify the scope**: What components were added/modified?
- **Understand the user impact**: How does this affect users/developers?
- **Note integration points**: What existing systems does this connect to?

### Step 2: Determine What Needs Updating

**README.md Updates** (minimal, high-level):

**architecture-overview.md Updates** (conceptual, moderate detail):

**functional-areas-design.md Updates** (detailed, technical):

### Step 3: Update Documentation Files

**Important:** Not all changes requires updates in all three documents.

**Update Order** (work from most detailed to least detailed):
1. **functional-areas-design.md** - Establish technical foundation
2. **architecture-overview.md** - Extract high-level concepts
3. **README.md** - Summarize key points

