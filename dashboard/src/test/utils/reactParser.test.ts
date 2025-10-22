import { describe, it, expect } from 'vitest'
import { parseReActMessage, parseThoughtAndAction } from '../../utils/reactParser'

describe('reactParser - parseReActMessage', () => {
  describe('Standard format with colons', () => {
    it('should parse complete ReAct message with all sections', () => {
      const content = `Thought: I need to investigate the issue
Action: get_logs
Action Input: pod: nginx-123
Observation: Found error logs
Final Answer: The pod has crashed due to OOM`

      const result = parseReActMessage(content)

      expect(result.thought).toBe('I need to investigate the issue')
      expect(result.action).toBe('get_logs')
      expect(result.actionInput).toBe('pod: nginx-123')
      expect(result.finalAnswer).toBe('The pod has crashed due to OOM')
    })

    it('should parse message with only thought and action', () => {
      const content = `Thought: Let me check the status
Action: kubectl_get_pods`

      const result = parseReActMessage(content)

      expect(result.thought).toBe('Let me check the status')
      expect(result.action).toBe('kubectl_get_pods')
      expect(result.actionInput).toBeUndefined()
      expect(result.finalAnswer).toBeUndefined()
    })

    it('should parse multi-line thought content', () => {
      const content = `Thought: I need to investigate this issue.
The user reported a crash.
I should check the logs first.

Action: get_logs
Action Input: pod: app-1`

      const result = parseReActMessage(content)

      expect(result.thought).toBe('I need to investigate this issue.\nThe user reported a crash.\nI should check the logs first.')
      expect(result.action).toBe('get_logs')
    })

    it('should handle case-insensitive section headers', () => {
      const content = `THOUGHT: Testing case insensitivity
ACTION: test_tool
ACTION INPUT: param: value
FINAL ANSWER: Test complete`

      const result = parseReActMessage(content)

      expect(result.thought).toBe('Testing case insensitivity')
      expect(result.action).toBe('test_tool')
      expect(result.actionInput).toBe('param: value')
      expect(result.finalAnswer).toBe('Test complete')
    })
  })

  describe('Malformed format without colons', () => {
    it('should parse malformed "Thought" without colon', () => {
      const content = `Thought
The user wants me to investigate a security alert.
I need to check the logs first.

Action: get_logs
Action Input: pod: suspicious-pod`

      const result = parseReActMessage(content)

      expect(result.thought).toBe('The user wants me to investigate a security alert.\nI need to check the logs first.')
      expect(result.action).toBe('get_logs')
      expect(result.actionInput).toBe('pod: suspicious-pod')
    })

    it('should parse real-world malformed example from user report', () => {
      const content = `Thought
The user wants me to investigate a security alert for the user \`danielzhe\`.
The alert indicates a \`suspicious\` activity related to \`-mining-\`.
The affected pod is \`dev-deployment-402waa2277-6ddff4f979-5xn4z\` in the \`danielzhe-dev\` namespace on the \`rm3\` cluster.

My investigation plan is as follows:
1. List all pods for the user \`danielzhe\` to get an overview of their workloads.
2. Examine the logs of the suspicious pod to understand its behavior.

Action: devsandbox-mcp-server.user-pods
Action Input: userSignup: danielzhe`

      const result = parseReActMessage(content)

      const expectedThought = `The user wants me to investigate a security alert for the user \`danielzhe\`.
The alert indicates a \`suspicious\` activity related to \`-mining-\`.
The affected pod is \`dev-deployment-402waa2277-6ddff4f979-5xn4z\` in the \`danielzhe-dev\` namespace on the \`rm3\` cluster.

My investigation plan is as follows:
1. List all pods for the user \`danielzhe\` to get an overview of their workloads.
2. Examine the logs of the suspicious pod to understand its behavior.`

      expect(result.thought).toBe(expectedThought)
      expect(result.action).toBe('devsandbox-mcp-server.user-pods')
      expect(result.actionInput).toBe('userSignup: danielzhe')
    })

    it('should NOT parse narrative text starting with "Thought" as a section', () => {
      const content = `Thought: I need to investigate the issue.
Thought about it for a moment and decided to proceed.
Let me check the logs.

Action: get_logs
Action Input: pod: app-1`

      const result = parseReActMessage(content)

      // Should capture everything from first "Thought:" to "Action:"
      expect(result.thought).toBe('I need to investigate the issue.\nThought about it for a moment and decided to proceed.\nLet me check the logs.')
      expect(result.action).toBe('get_logs')
    })

    it('should handle mid-line Final Answer with malformed Thought (no colon)', () => {
      const content = `Thought
The configuration file confirms the application is running version 2.3.4 of the standard web server.

I have enough information to provide a final answer.Final Answer:
**System Status Summary**: The application is operating normally with expected resource utilization patterns.

Recommended Action: MONITOR

**Confidence Level**: HIGH`

      const result = parseReActMessage(content)

      expect(result.thought).toBe('The configuration file confirms the application is running version 2.3.4 of the standard web server.\n\nI have enough information to provide a final answer.')
      expect(result.finalAnswer).toBe('**System Status Summary**: The application is operating normally with expected resource utilization patterns.\n\nRecommended Action: MONITOR\n\n**Confidence Level**: HIGH')
    })
  })

  describe('Edge cases', () => {
    it('should handle empty string', () => {
      const result = parseReActMessage('')

      expect(result.thought).toBeUndefined()
      expect(result.action).toBeUndefined()
      expect(result.actionInput).toBeUndefined()
      expect(result.finalAnswer).toBeUndefined()
    })

    it('should handle message with only Final Answer', () => {
      const content = `Final Answer: The analysis is complete`

      const result = parseReActMessage(content)

      expect(result.thought).toBeUndefined()
      expect(result.action).toBeUndefined()
      expect(result.finalAnswer).toBe('The analysis is complete')
    })

    it('should handle extra whitespace and newlines', () => {
      const content = `

Thought:    I need to check this   

Action:   get_status  
Action Input:   namespace: default  

`

      const result = parseReActMessage(content)

      expect(result.thought).toBe('I need to check this')
      expect(result.action).toBe('get_status')
      expect(result.actionInput).toBe('namespace: default')
    })

    it('should handle multi-line Action Input', () => {
      const content = `Thought: Running a complex query
Action: execute_query
Action Input: {
  "query": "SELECT * FROM users",
  "limit": 100
}`

      const result = parseReActMessage(content)

      expect(result.thought).toBe('Running a complex query')
      expect(result.action).toBe('execute_query')
      expect(result.actionInput).toBe('{\n  "query": "SELECT * FROM users",\n  "limit": 100\n}')
    })
  })
})

describe('reactParser - parseThoughtAndAction', () => {
  describe('Standard format with colons', () => {
    it('should extract thought and action from standard format', () => {
      const content = `Thought: I need to check the logs
Action: get_logs
Action Input: pod: nginx`

      const result = parseThoughtAndAction(content)

      expect(result.thought).toBe('I need to check the logs')
      expect(result.action).toBe('get_logs\nAction Input: pod: nginx')
    })

    it('should handle multi-line thought', () => {
      const content = `Thought: First line
Second line
Third line

Action: test_action`

      const result = parseThoughtAndAction(content)

      expect(result.thought).toBe('First line\nSecond line\nThird line')
      expect(result.action).toBe('test_action')
    })

    it('should handle case-insensitive headers', () => {
      const content = `THOUGHT: Testing case
ACTION: test_tool`

      const result = parseThoughtAndAction(content)

      expect(result.thought).toBe('Testing case')
      expect(result.action).toBe('test_tool')
    })
  })

  describe('Malformed format without colons', () => {
    it('should extract thought from malformed "Thought" without colon', () => {
      const content = `Thought
The user wants me to investigate.
I will start by checking the logs.

Action: get_logs`

      const result = parseThoughtAndAction(content)

      expect(result.thought).toBe('The user wants me to investigate.\nI will start by checking the logs.')
      expect(result.action).toBe('get_logs')
    })

    it('should handle real-world malformed example', () => {
      const content = `Thought
The user wants me to investigate a security alert for the user \`danielzhe\`.

My investigation plan:
1. Check the logs
2. Review the metrics

Action: investigate_user
Action Input: user: danielzhe`

      const result = parseThoughtAndAction(content)

      const expectedThought = `The user wants me to investigate a security alert for the user \`danielzhe\`.

My investigation plan:
1. Check the logs
2. Review the metrics`

      expect(result.thought).toBe(expectedThought)
      expect(result.action).toBe('investigate_user\nAction Input: user: danielzhe')
    })

    it('should handle mid-line Final Answer with malformed Thought (no colon)', () => {
      const content = `Thought
The configuration file confirms the application is running version 2.3.4 of the standard web server.

I have enough information to provide a final answer.Final Answer:
**System Status Summary**: The application is operating normally.`

      const result = parseThoughtAndAction(content)

      expect(result.thought).toBe('The configuration file confirms the application is running version 2.3.4 of the standard web server.\n\nI have enough information to provide a final answer.')
      expect(result.action).toBe('')
    })
  })

  describe('Edge cases', () => {
    it('should return empty strings for empty input', () => {
      const result = parseThoughtAndAction('')

      expect(result.thought).toBe('')
      expect(result.action).toBe('')
    })

    it('should handle message with only thought', () => {
      const content = `Thought: Just thinking about the problem`

      const result = parseThoughtAndAction(content)

      expect(result.thought).toBe('Just thinking about the problem')
      expect(result.action).toBe('')
    })

    it('should handle message with only action', () => {
      const content = `Action: execute_command`

      const result = parseThoughtAndAction(content)

      expect(result.thought).toBe('')
      expect(result.action).toBe('execute_command')
    })

    it('should handle text before Thought section', () => {
      const content = `Some preamble text

Thought: Now I will think
Action: now_act`

      const result = parseThoughtAndAction(content)

      expect(result.thought).toBe('Now I will think')
      expect(result.action).toBe('now_act')
    })

    it('should trim whitespace from extracted content', () => {
      const content = `Thought:    Lots of spaces    

Action:   spaced_action  `

      const result = parseThoughtAndAction(content)

      expect(result.thought).toBe('Lots of spaces')
      expect(result.action).toBe('spaced_action')
    })
  })

  describe('Consistency with parseReActMessage', () => {
    it('should extract same thought as parseReActMessage for standard format', () => {
      const content = `Thought: I need to investigate
Action: check_status
Action Input: pod: app-1`

      const full = parseReActMessage(content)
      const light = parseThoughtAndAction(content)

      expect(light.thought).toBe(full.thought)
    })

    it('should extract same thought for malformed format', () => {
      const content = `Thought
The user wants me to check something.

Action: check_tool
Action Input: param: value`

      const full = parseReActMessage(content)
      const light = parseThoughtAndAction(content)

      expect(light.thought).toBe(full.thought)
    })
  })
})

