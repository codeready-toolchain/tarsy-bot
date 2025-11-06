# Chat Message Templates for E2E Tests

This directory contains expected chat message content templates for E2E testing of the TARSy chat functionality.

## Purpose

Chat messages include dynamically generated investigation history that can be quite large. To improve test maintainability and readability, these templates are stored in separate files rather than inline in the test code.

## Files

### `chat_msg1_user_history.txt`
The investigation history context for the **first chat message** in the E2E test flow.

**Contains:**
- Original alert investigation (from the final analysis stage)
- Results from all previous stages (data-collection, verification, analysis)
- The first chat question: "Can you check the pods in the stuck-namespace?"

### `chat_msg2_user_history.txt`
The investigation history context for the **second chat message** (follow-up) in the E2E test flow.

**Contains:**
- Everything from `chat_msg1_user_history.txt`
- PLUS the first chat message exchange (question + assistant's response about pods)
- The second chat question: "Does the namespace still exist?"

## How These Templates Are Generated

These templates match the actual LLM conversation history that the ChatAgent constructs when processing follow-up questions. The history includes:

1. **Investigation Context**: The complete investigation from the session, formatted for LLM consumption
2. **Previous Chat Messages**: For subsequent messages, includes all previous chat exchanges
3. **Current Question**: The user's follow-up question

## Updating Templates

If you modify:
- The alert processing stages (data-collection, verification, analysis)
- The chat history formatting logic in `ChatController`
- The mock responses in `test_api_e2e.py`

You may need to update these templates. To capture the actual content:

1. **Enable debug mode** in `test_api_e2e.py` by adding debug output:
   ```python
   # In assert_chat_conversation_messages(), add before assertion:
   if expected_content != actual_content:
       import os
       os.makedirs("/tmp/tarsy_test_debug", exist_ok=True)
       with open(f"/tmp/tarsy_test_debug/chat_msg_{i}_actual.txt", "w") as f:
           f.write(actual_content)
   ```

2. **Run the E2E test**:
   ```bash
   make test-e2e
   ```

3. **Copy the actual content** to the template file:
   ```bash
   cp /tmp/tarsy_test_debug/chat_msg_1_actual.txt chat_msg1_user_history.txt
   ```

4. **Remove debug code** and verify tests pass

## Notes

- Templates should NOT have trailing newlines (they are stripped by `load_chat_message_template()`)
- The content includes the exact formatting, line breaks, and structure used by the chat system
- Email addresses in the content are masked with `__MASKED_EMAIL__` for security
- Timestamps are represented as `{TIMESTAMP}` placeholders

