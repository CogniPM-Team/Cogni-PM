import type { components } from './schema'

// Named once here so the rest of the app never reaches into the generated file. They are generated from the
// backend (`npm run gen:api`), so renaming a field there is a compile error here.
type Schemas = components['schemas']

export type RunSummary = Schemas['RunSummary']
export type RunDetail = Schemas['RunDetail']
export type RunList = Schemas['RunList']
export type Draft = Schemas['DraftOut']
export type Step = Schemas['StepOut']
export type SourceSpan = Schemas['SourceSpan']
export type ChangeEdit = Schemas['ChangeEdit']
export type ApproveResult = Schemas['ApproveResult']
export type ApplyProblem = Schemas['ApplyProblem']
export type StartedRun = Schemas['StartedRun']
export type RerunResult = Schemas['RerunResult']
export type ChatResult = Schemas['ChatResult']
export type AuditRow = Schemas['AuditRow']
export type AuditPage = Schemas['AuditPage']
export type Mode = Schemas['ModeOut']
export type Story = Schemas['StoryOut']
export type Project = Schemas['ProjectOut']
export type StartRunBody = Schemas['StartRunBody']

export type AuditFilter = AuditPage['filter']
