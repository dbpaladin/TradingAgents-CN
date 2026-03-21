/**
 * A股回测 API 封装
 */

import { request, type ApiResponse } from './request'

// ===== 类型定义 =====

export interface BacktestConfig {
  symbol: string
  stock_name?: string
  start_date: string
  end_date: string
  initial_capital?: number
  position_ratio?: number
  position_strategy?: 'full' | 'half' | 'fixed'
  commission_rate?: number
  stamp_duty_rate?: number
  min_commission?: number
  selected_analysts?: string[]
  research_depth?: string
  quick_analysis_model?: string
  deep_analysis_model?: string
  decision_interval_days?: number
  name?: string
  description?: string
}

export interface BacktestCreateRequest {
  config: BacktestConfig
}

export type BacktestStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface BacktestTaskStatus {
  task_id: string
  status: BacktestStatus
  progress: number
  current_date: string | null
  current_step: string | null
  symbol: string
  start_date: string
  end_date: string
  created_at: string | null
  started_at: string | null
  completed_at: string | null
  error_message: string | null
}

export interface TradeRecord {
  date: string
  action: 'BUY' | 'SELL' | 'HOLD'
  price: number
  shares: number
  amount: number
  commission: number
  stamp_duty: number
  total_cost: number
  cash: number
  position_shares: number
  position_value: number
  total_assets: number
  ai_signal: string
  ai_confidence: number
  ai_reason: string
  t1_restriction: boolean
  limit_up: boolean
  limit_down: boolean
  executed: boolean
}

export interface DailyEquity {
  date: string
  total_assets: number
  cash: number
  position_value: number
  equity_ratio: number
  benchmark_ratio: number
  drawdown: number
}

export interface BacktestMetrics {
  total_return: number
  annual_return: number
  benchmark_return: number
  excess_return: number
  max_drawdown: number
  sharpe_ratio: number
  volatility: number
  total_trades: number
  buy_trades: number
  sell_trades: number
  win_trades: number
  lose_trades: number
  win_rate: number
  avg_holding_days: number
  total_commission: number
  total_stamp_duty: number
  total_fees: number
  final_assets: number
  initial_capital: number
  profit_loss: number
  trading_days: number
  start_date: string
  end_date: string
}

export interface BacktestResult {
  task_id: string
  symbol: string
  stock_name: string | null
  metrics: BacktestMetrics
  trades: TradeRecord[]
  daily_equity: DailyEquity[]
  created_at: string
}

export interface BacktestTaskListItem {
  task_id: string
  status: BacktestStatus
  progress: number
  symbol: string
  stock_name: string | null
  start_date: string
  end_date: string
  name: string
  created_at: string | null
  completed_at: string | null
  error_message: string | null
  total_return: number | null
  max_drawdown: number | null
}

// ===== API 方法 =====

export const backtestApi = {
  /** 提交回测任务 */
  createTask(request_: BacktestCreateRequest): Promise<ApiResponse<{ task_id: string; status: string; message: string }>> {
    return request.post('/api/backtest/tasks', request_)
  },

  /** 查询回测任务状态 */
  getTaskStatus(taskId: string): Promise<ApiResponse<BacktestTaskStatus>> {
    return request.get(`/api/backtest/tasks/${taskId}`)
  },

  /** 获取完整回测结果 */
  getTaskResult(taskId: string): Promise<ApiResponse<BacktestResult>> {
    return request.get(`/api/backtest/tasks/${taskId}/result`)
  },

  /** 获取任务列表 */
  listTasks(params?: { limit?: number; offset?: number }): Promise<ApiResponse<{ tasks: BacktestTaskListItem[]; total: number }>> {
    return request.get('/api/backtest/tasks', { params })
  },

  /** 删除回测任务 */
  deleteTask(taskId: string): Promise<ApiResponse<null>> {
    return request.delete(`/api/backtest/tasks/${taskId}`)
  }
}
