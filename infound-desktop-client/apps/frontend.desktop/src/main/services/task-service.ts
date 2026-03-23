import { BaseApiResponse } from '../utils/net-request'
import openapiRequest from './base/open-api-service'
import { template } from 'radash'
import { API_ENDPOINTS } from './endpoints'

export enum TaskType {
  Outreach = 'OUTREACH',
  CreatorDetail = 'CREATOR_DETAIL',
  SampleMonitor = 'SAMPLE_MONITOR', // camelCase 字段传入 body
  Chat = 'CHAT'
}

export enum TaskStatus {
  Pending = 'PENDING',
  Running = 'RUNNING',
  Completed = 'COMPLETED',
  Failed = 'FAILED',
  Cancelled = 'CANCELLED'
}

// TODO: 后续细化调整
export interface TaskInfo {
  id: string
  task_type: TaskType
  task_status: TaskStatus
  task_data: unknown
  created_at: string
  updated_at: string
}

export async function claimTaskAsync(taskType: TaskType): Promise<BaseApiResponse<TaskInfo>> {
  const url = API_ENDPOINTS.task.claim + `?task_type=${taskType}`
  return await openapiRequest.get<BaseApiResponse<TaskInfo>>(url)
}

export async function heartbeatAsync(taskId: string): Promise<BaseApiResponse<Record<string, any>>> {
  const url = template(API_ENDPOINTS.task.heartbeat, { taskId: taskId })
  return await openapiRequest.post<BaseApiResponse>(url)
}

export async function reportAsync(taskId: string, taskStatus: TaskStatus, error?: string): Promise<BaseApiResponse<Record<string, any>>> {
  const url = template(API_ENDPOINTS.task.report, { taskId: taskId })
  const payload = {
    task_status: taskStatus,
    error
  }
  return await openapiRequest.post<BaseApiResponse>(url, payload)
}
