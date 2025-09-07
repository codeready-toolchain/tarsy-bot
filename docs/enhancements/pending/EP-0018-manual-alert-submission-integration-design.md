# EP-0018: Manual Alert Submission Integration Design

## Problem Statement

Currently, manual alert submission is handled by a separate `alert-dev-ui` React application, which creates:
- **Maintenance Overhead**: Two separate React applications to maintain
- **User Experience Fragmentation**: Users must navigate between different applications for alert monitoring vs. submission
- **Development Complexity**: Duplicate dependencies, build processes, and deployment configurations
- **Limited Feature Integration**: No shared state or components between monitoring dashboard and alert submission

## Solution Overview

Integrate the manual alert submission functionality from `alert-dev-ui` directly into the main dashboard application as a new page/route. This consolidates the user experience into a single application while maintaining the flexible alert submission capabilities.

## Key Design Decisions

### 1. Integration Approach
- **Merge Strategy**: Copy and adapt components from `alert-dev-ui` into the dashboard
- **Navigation**: Add new route `/submit-alert` to existing dashboard routing, opens in new tab
- **Feature Completeness**: Preserve all existing alert submission functionality
- **UI Consistency**: Adapt Material-UI components to match dashboard theme

### 2. Access Control & Settings
- **Production Ready**: Not a development-only feature, suitable for production use
- **Always Available**: Feature is always enabled (optional disable functionality to be addressed later)

### 3. User Interface

#### Navigation Menu Item
- **Location**: Add hamburger menu or navigation drawer
- **Style**: Menu item "Manual Alert Submission". Opens a new browser tab.
- **Benefits**: Clean header, expandable navigation structure

## Technical Architecture

### Frontend Changes
```typescript
// New route in App.tsx (opened via new tab from navigation menu)
<Route path="/submit-alert" element={<ManualAlertSubmission />} />

// New components to create/migrate:
// - components/ManualAlertSubmission.tsx (main page, no back button)
// - components/ManualAlertForm.tsx (form component)
// - components/AlertSubmissionStatus.tsx (processing status, "Submit Another" option)
```

### Component Migration Strategy
1. **AlertForm**: Adapt existing form component to dashboard theme
2. **ProcessingStatus**: Reuse WebSocket integration (updates only on alert completion)
3. **API Integration**: Leverage existing dashboard API client
4. **State Management**: Integrate with dashboard's state patterns
5. **Navigation**: Menu item opens new tab, no back button needed
6. **Completion Flow**: "Submit Another Alert" option when processing completes

## User Experience Flow

1. **Access**: User clicks navigation menu item from main dashboard, opens in new browser tab
2. **Form**: User fills out alert type, runbook URL, and flexible key-value pairs  
3. **Submission**: Alert submits using existing backend API
4. **Processing**: Real-time status updates using WebSocket connection (updates only when alert completes)
5. **Completion**: Option to submit another alert (no back button needed since opened in new tab)
6. **Integration**: Submitted alerts appear in main dashboard's active/historical sessions

## Runtime Behavior
- **Always Available**: Navigation elements always visible, route always accessible
- **API Endpoint**: Uses existing alert submission API endpoints

## Migration Strategy

### Phase 1: Component Integration
1. Create new dashboard route and page component
2. Migrate and adapt form components from alert-dev-ui
3. Integrate with dashboard's API client and WebSocket services

### Phase 2: UI Integration
1. Add chosen navigation element to dashboard
2. Ensure consistent theming and user experience
3. Test integration with existing dashboard features

### Phase 3: Cleanup
1. Remove alert-dev-ui directory and related build processes
2. Update documentation and deployment procedures

## Benefits

1. **Unified User Experience**: Single application for all alert-related workflows
2. **Reduced Maintenance**: One React application, shared dependencies
3. **Enhanced Integration**: Shared state, WebSocket connections, and API clients
4. **Simplified Deployment**: Single build process and deployment target
5. **Consistent Theming**: Unified Material-UI theme across all features

## Success Criteria

1. **Feature Parity**: All alert-dev-ui functionality preserved
2. **UI Consistency**: Matches dashboard theme and patterns
3. **Performance**: No noticeable impact on dashboard performance
4. **Navigation**: Menu item opens submission page in new tab
5. **WebSocket Integration**: Real-time updates only when alert completes
6. **Completion Flow**: "Submit Another Alert" option available after processing
7. **Clean Migration**: Complete removal of alert-dev-ui without functionality loss
