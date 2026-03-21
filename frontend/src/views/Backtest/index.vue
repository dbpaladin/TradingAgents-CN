<template>
  <div class="backtest-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon class="title-icon"><DataAnalysis /></el-icon>
        A股策略回测
      </h1>
      <p class="page-subtitle">使用 AI 多智能体分析在历史行情上模拟交易，评估策略有效性</p>
    </div>

    <el-row :gutter="20">
      <!-- 左栏：配置面板 + 历史任务 -->
      <el-col :lg="8" :md="10" :sm="24">
        <!-- 配置面板 -->
        <el-card class="config-card" shadow="never">
          <template #header>
            <div class="card-header">
              <el-icon><Setting /></el-icon>
              <span>回测配置</span>
            </div>
          </template>

          <el-form :model="form" :rules="rules" ref="formRef" label-position="top" class="config-form">
            <!-- 股票代码 -->
            <el-form-item label="股票代码" prop="symbol">
              <el-input
                v-model="form.symbol"
                placeholder="如: 000001 或 600519"
                clearable
                :prefix-icon="Search"
              >
                <template #append>
                  <el-button @click="fetchStockName" :loading="loadingName" text>查询</el-button>
                </template>
              </el-input>
              <div v-if="stockName" class="stock-name-hint">
                <el-tag size="small" type="success">{{ stockName }}</el-tag>
              </div>
            </el-form-item>

            <!-- 回测区间 -->
            <el-form-item label="回测区间" prop="dateRange">
              <el-date-picker
                v-model="form.dateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                :disabled-date="disabledDate"
                style="width: 100%"
              />
            </el-form-item>

            <!-- 初始资金 -->
            <el-form-item label="初始资金（元）" prop="initial_capital">
              <el-input-number
                v-model="form.initial_capital"
                :min="10000"
                :max="10000000"
                :step="10000"
                :precision="0"
                controls-position="right"
                style="width: 100%"
              />
            </el-form-item>

            <!-- 每次仓位比例 -->
            <el-form-item label="买入仓位比例">
              <div class="slider-row">
                <el-slider v-model="form.position_ratio_pct" :min="10" :max="100" :step="10" style="flex: 1" />
                <span class="slider-label">{{ form.position_ratio_pct }}%</span>
              </div>
            </el-form-item>

            <!-- 选择分析师 -->
            <el-form-item label="AI 分析师（建议只选2个以控制成本）">
              <el-checkbox-group v-model="form.selected_analysts">
                <el-checkbox label="market">市场分析</el-checkbox>
                <el-checkbox label="fundamentals">基本面</el-checkbox>
                <el-checkbox label="sentiment">情绪面</el-checkbox>
                <el-checkbox label="theme_rotation">题材轮动</el-checkbox>
                <el-checkbox label="institutional_theme">机构布局题材</el-checkbox>
                <el-checkbox label="news">新闻</el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <!-- 研究深度 -->
            <el-form-item label="研究深度">
              <el-radio-group v-model="form.research_depth">
                <el-radio label="快速">快速（省Token）</el-radio>
                <el-radio label="深度">深度（耗时长）</el-radio>
              </el-radio-group>
            </el-form-item>

            <!-- AI模型配置 -->
            <el-form-item label="快速分析模型">
              <el-select
                v-model="form.quick_analysis_model"
                filterable
                placeholder="选择快速分析模型"
                style="width: 100%"
                :loading="loadingModels"
              >
                <el-option
                  v-for="model in availableModels"
                  :key="`quick-${model.provider}-${model.model_name}`"
                  :label="modelLabel(model)"
                  :value="model.model_name"
                >
                  <div class="model-option">
                    <span class="model-option-name">{{ model.model_display_name || model.model_name }}</span>
                    <span class="model-option-provider">{{ model.provider }}</span>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>

            <el-form-item label="深度决策模型">
              <el-select
                v-model="form.deep_analysis_model"
                filterable
                placeholder="选择深度决策模型"
                style="width: 100%"
                :loading="loadingModels"
              >
                <el-option
                  v-for="model in availableModels"
                  :key="`deep-${model.provider}-${model.model_name}`"
                  :label="modelLabel(model)"
                  :value="model.model_name"
                >
                  <div class="model-option">
                    <span class="model-option-name">{{ model.model_display_name || model.model_name }}</span>
                    <span class="model-option-provider">{{ model.provider }}</span>
                  </div>
                </el-option>
              </el-select>
              <div class="model-hint">不选时会使用系统默认模型；这里可以为本次回测单独指定模型。</div>
            </el-form-item>

            <!-- 回测名称 -->
            <el-form-item label="回测名称（可选）">
              <el-input v-model="form.name" placeholder="为此次回测起个名字" maxlength="50" show-word-limit />
            </el-form-item>

            <!-- 费用预估提示 -->
            <el-alert type="warning" :closable="false" class="cost-alert">
              <template #title>
                <span>💰 费用预估：约 {{ estimatedTradingDays }} 个交易日 × {{ form.selected_analysts.length }} 位分析师</span>
              </template>
              建议先用"快速"深度 + 2 位分析师测试，以控制 Token 消耗。
            </el-alert>

            <!-- 提交按钮 -->
            <el-button
              type="primary"
              :loading="submitting"
              @click="submitBacktest"
              class="submit-btn"
              :disabled="!canSubmit"
            >
              <el-icon><VideoPlay /></el-icon>
              开始回测
            </el-button>
          </el-form>
        </el-card>

        <!-- 历史回测任务 -->
        <el-card class="history-card" shadow="never" style="margin-top: 16px">
          <template #header>
            <div class="card-header">
              <el-icon><Clock /></el-icon>
              <span>历史回测</span>
              <el-button link @click="loadTaskHistory" :loading="loadingHistory" class="refresh-btn">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </template>

          <div v-if="taskHistory.length === 0 && !loadingHistory" class="empty-history">
            <el-empty description="暂无回测记录" :image-size="60" />
          </div>

          <div v-else class="history-list">
            <div
              v-for="task in taskHistory"
              :key="task.task_id"
              class="history-item"
              :class="{ active: currentTaskId === task.task_id }"
              @click="selectTask(task)"
            >
              <div class="history-item-header">
                <span class="history-symbol">{{ task.symbol }}</span>
                <el-tag :type="statusTagType(task.status)" size="small">{{ statusLabel(task.status) }}</el-tag>
              </div>
              <div class="history-item-meta">
                <span>{{ task.start_date }} ~ {{ task.end_date }}</span>
              </div>
              <div v-if="task.total_return !== null" class="history-item-return" :class="task.total_return >= 0 ? 'positive' : 'negative'">
                {{ task.total_return >= 0 ? '+' : '' }}{{ task.total_return?.toFixed(2) }}%
              </div>
              <el-progress
                v-if="task.status === 'running'"
                :percentage="task.progress"
                :stroke-width="4"
                size="small"
                status="warning"
                striped-flow
                :duration="10"
              />
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右栏：运行进度 + 结果展示 -->
      <el-col :lg="16" :md="14" :sm="24">
        <!-- 运行进度面板 -->
        <el-card v-if="runningTaskStatus" class="progress-card" shadow="never">
          <template #header>
            <div class="card-header">
              <el-icon class="spin-icon"><Loading /></el-icon>
              <span>正在回测：{{ runningTaskStatus.symbol }}</span>
            </div>
          </template>
          <el-progress
            :percentage="runningTaskStatus.progress"
            :stroke-width="16"
            striped
            striped-flow
            :duration="10"
            class="main-progress"
          />
          <div class="progress-detail">
            <el-icon><Calendar /></el-icon>
            <span>当前日期：<strong>{{ runningTaskStatus.current_date || '准备中...' }}</strong></span>
          </div>
          <div class="progress-step">{{ runningTaskStatus.current_step }}</div>
        </el-card>

        <!-- 失败状态 -->
        <el-card v-if="failedErrorMsg" class="error-card" shadow="never">
          <el-alert type="error" :title="'回测失败: ' + failedErrorMsg" :closable="false" show-icon />
        </el-card>

        <!-- 结果看板 -->
        <template v-if="backtestResult">
          <!-- 指标摘要卡片行 -->
          <el-row :gutter="12" class="metrics-row">
            <el-col :span="6">
              <div class="metric-card" :class="backtestResult.metrics.total_return >= 0 ? 'positive' : 'negative'">
                <div class="metric-label">总收益率</div>
                <div class="metric-value">{{ formatPct(backtestResult.metrics.total_return) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="metric-card" :class="backtestResult.metrics.annual_return >= 0 ? 'positive' : 'negative'">
                <div class="metric-label">年化收益率</div>
                <div class="metric-value">{{ formatPct(backtestResult.metrics.annual_return) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="metric-card neutral">
                <div class="metric-label">最大回撤</div>
                <div class="metric-value negative">-{{ formatPct(backtestResult.metrics.max_drawdown) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="metric-card neutral">
                <div class="metric-label">夏普比率</div>
                <div class="metric-value" :class="backtestResult.metrics.sharpe_ratio >= 0 ? 'positive' : 'negative'">
                  {{ backtestResult.metrics.sharpe_ratio.toFixed(3) }}
                </div>
              </div>
            </el-col>
          </el-row>

          <el-row :gutter="12" class="metrics-row">
            <el-col :span="6">
              <div class="metric-card neutral">
                <div class="metric-label">胜率</div>
                <div class="metric-value">{{ formatPct(backtestResult.metrics.win_rate) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="metric-card neutral">
                <div class="metric-label">总交易次数</div>
                <div class="metric-value">{{ backtestResult.metrics.total_trades }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="metric-card" :class="backtestResult.metrics.excess_return >= 0 ? 'positive' : 'negative'">
                <div class="metric-label">超额收益（vs上证）</div>
                <div class="metric-value">{{ formatPct(backtestResult.metrics.excess_return) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="metric-card neutral">
                <div class="metric-label">总费用</div>
                <div class="metric-value negative">{{ formatMoney(backtestResult.metrics.total_fees) }}</div>
              </div>
            </el-col>
          </el-row>

          <!-- 净值曲线图 -->
          <el-card class="chart-card" shadow="never">
            <template #header>
              <div class="card-header">
                <el-icon><TrendCharts /></el-icon>
                <span>资产净值曲线</span>
                <el-tag size="small" type="info">对比上证指数基准</el-tag>
              </div>
            </template>
            <div ref="chartRef" class="equity-chart"></div>
          </el-card>

          <!-- 交易明细 -->
          <el-card class="trades-card" shadow="never" style="margin-top: 16px">
            <template #header>
              <div class="card-header">
                <el-icon><List /></el-icon>
                <span>交易明细（{{ executedTrades.length }} 笔）</span>
              </div>
            </template>
            <el-table
              :data="executedTrades"
              size="small"
              stripe
              :max-height="400"
            >
              <el-table-column prop="date" label="日期" width="110" />
              <el-table-column prop="action" label="方向" width="72">
                <template #default="{ row }">
                  <el-tag :type="row.action === 'BUY' ? 'danger' : 'success'" size="small">
                    {{ row.action === 'BUY' ? '买入' : row.action === 'SELL' ? '卖出' : '持有' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="price" label="价格" width="80">
                <template #default="{ row }">{{ row.price.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column prop="shares" label="股数" width="80" />
              <el-table-column prop="amount" label="金额" width="100">
                <template #default="{ row }">{{ formatMoney(row.amount) }}</template>
              </el-table-column>
              <el-table-column prop="total_assets" label="总资产" width="110">
                <template #default="{ row }">{{ formatMoney(row.total_assets) }}</template>
              </el-table-column>
              <el-table-column prop="ai_reason" label="AI决策依据" show-overflow-tooltip />
              <el-table-column label="限制" width="80">
                <template #default="{ row }">
                  <el-tag v-if="row.t1_restriction" size="small" type="warning">T+1</el-tag>
                  <el-tag v-if="row.limit_up" size="small" type="danger">涨停</el-tag>
                  <el-tag v-if="row.limit_down" size="small" type="info">跌停</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </template>

        <!-- 空状态提示 -->
        <el-card v-if="!backtestResult && !runningTaskStatus && !failedErrorMsg" class="empty-card" shadow="never">
          <el-empty description="配置好参数后点击「开始回测」，AI将在历史行情上模拟交易">
            <template #image>
              <el-icon style="font-size: 80px; color: var(--el-color-primary-light-5)"><DataAnalysis /></el-icon>
            </template>
          </el-empty>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import {
  DataAnalysis, Setting, Search, VideoPlay, Clock, Refresh,
  Loading, Calendar, TrendCharts, List
} from '@element-plus/icons-vue'
import { backtestApi, type BacktestTaskStatus, type BacktestResult, type BacktestTaskListItem } from '@/api/backtest'
import { configApi, type LLMConfig } from '@/api/config'

// ===== 表单状态 =====
const formRef = ref()
const form = ref({
  symbol: '',
  dateRange: [] as string[],
  initial_capital: 100000,
  position_ratio_pct: 100,            // 百分比（1-100）
  selected_analysts: ['market', 'fundamentals'],
  research_depth: '快速',
  quick_analysis_model: '',
  deep_analysis_model: '',
  name: ''
})

const rules = {
  symbol: [{ required: true, message: '请输入股票代码', trigger: 'blur' }],
  dateRange: [{ required: true, message: '请选择回测区间', trigger: 'change' }],
  initial_capital: [{ required: true, message: '请输入初始资金', trigger: 'blur' }]
}

const stockName = ref('')
const loadingName = ref(false)
const submitting = ref(false)
const loadingModels = ref(false)
const route = useRoute()
const router = useRouter()
const availableModels = ref<LLMConfig[]>([])

// ===== 任务状态 =====
const currentTaskId = ref<string | null>(null)
const runningTaskStatus = ref<BacktestTaskStatus | null>(null)
const backtestResult = ref<BacktestResult | null>(null)
const failedErrorMsg = ref<string | null>(null)
const taskHistory = ref<BacktestTaskListItem[]>([])
const loadingHistory = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null

// ===== ECharts =====
const chartRef = ref<HTMLElement>()
let chartInstance: any = null

// ===== 计算属性 =====
const canSubmit = computed(() =>
  form.value.symbol && form.value.dateRange.length === 2 && form.value.selected_analysts.length > 0
)

const estimatedTradingDays = computed(() => {
  if (form.value.dateRange.length < 2) return 0
  const start = new Date(form.value.dateRange[0])
  const end = new Date(form.value.dateRange[1])
  const days = Math.ceil((end.getTime() - start.getTime()) / (1000 * 86400))
  return Math.round(days * 5 / 7)  // 粗略估算
})

const executedTrades = computed(() =>
  (backtestResult.value?.trades || []).filter(t => t.executed)
)

// ===== 方法 =====
function disabledDate(d: Date) {
  return d > new Date()
}

function statusTagType(status: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    pending: 'info', running: 'warning', completed: 'success', failed: 'danger', cancelled: 'info'
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '等待中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消'
  }
  return map[status] || status
}

function formatPct(val: number) {
  return (val >= 0 ? '+' : '') + val.toFixed(2) + '%'
}

function formatMoney(val: number) {
  if (val >= 10000) return (val / 10000).toFixed(2) + '万'
  return val.toFixed(2)
}

function modelLabel(model: LLMConfig) {
  const displayName = (model as any).model_display_name || model.model_name
  return `${displayName} (${model.provider})`
}

async function initializeModelSettings() {
  loadingModels.value = true
  try {
    const [defaultModels, llmConfigs] = await Promise.all([
      configApi.getDefaultModels(),
      configApi.getLLMConfigs()
    ])

    availableModels.value = llmConfigs.filter((config: any) => config.enabled ?? config.is_active ?? true)
    form.value.quick_analysis_model = defaultModels.quick_analysis_model || 'qwen-turbo'
    form.value.deep_analysis_model = defaultModels.deep_analysis_model || 'qwen-max'
  } catch (error) {
    console.error('加载回测模型配置失败:', error)
    form.value.quick_analysis_model = 'qwen-turbo'
    form.value.deep_analysis_model = 'qwen-max'
    ElMessage.warning('模型列表加载失败，已回退到默认模型')
  } finally {
    loadingModels.value = false
  }
}

async function fetchStockName() {
  if (!form.value.symbol) return
  loadingName.value = true
  try {
    // 使用 AkShare 搜索接口获取股票名称
    const res = await fetch(`/api/stocks/search?keyword=${form.value.symbol}&market=A股`)
    if (res.ok) {
      const data = await res.json()
      const items = data?.data?.stocks || []
      if (items.length > 0) {
        stockName.value = items[0].name || ''
      }
    }
  } catch {
    // silently fail
  } finally {
    loadingName.value = false
  }
}

async function submitBacktest() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  submitting.value = true
  failedErrorMsg.value = null
  backtestResult.value = null
  runningTaskStatus.value = null

  try {
    const res = await backtestApi.createTask({
      config: {
        symbol: form.value.symbol.trim(),
        stock_name: stockName.value || undefined,
        start_date: form.value.dateRange[0],
        end_date: form.value.dateRange[1],
        initial_capital: form.value.initial_capital,
        position_ratio: form.value.position_ratio_pct / 100,
        selected_analysts: form.value.selected_analysts,
        research_depth: form.value.research_depth,
        quick_analysis_model: form.value.quick_analysis_model || undefined,
        deep_analysis_model: form.value.deep_analysis_model || undefined,
        name: form.value.name
      }
    })

    const taskId = res.data?.task_id || (res as any).task_id
    if (!taskId) throw new Error('未获取到任务ID')

    currentTaskId.value = taskId
    ElMessage.success(`回测任务已提交: ${taskId}`)
    startPolling(taskId)
    await loadTaskHistory()
  } catch (e: any) {
    ElMessage.error('提交失败: ' + (e.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}

function startPolling(taskId: string) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const res = await backtestApi.getTaskStatus(taskId)
      const status = res.data || (res as any)

      if (status.status === 'running' || status.status === 'pending') {
        runningTaskStatus.value = status
      } else if (status.status === 'completed') {
        runningTaskStatus.value = null
        stopPolling()
        await loadResult(taskId)
        await loadTaskHistory()
      } else if (status.status === 'failed') {
        runningTaskStatus.value = null
        failedErrorMsg.value = status.error_message || '回测执行失败'
        stopPolling()
        await loadTaskHistory()
      }
    } catch (e) {
      console.error('轮询状态失败:', e)
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function loadResult(taskId: string) {
  try {
    const res = await backtestApi.getTaskResult(taskId)
    backtestResult.value = (res.data || res) as BacktestResult
    await nextTick()
    renderChart()
  } catch (e: any) {
    ElMessage.error('获取结果失败: ' + e.message)
  }
}

async function loadTaskHistory(options?: { autoResumeRunning?: boolean }) {
  const autoResumeRunning = options?.autoResumeRunning ?? true
  loadingHistory.value = true
  try {
    const res = await backtestApi.listTasks({ limit: 20 })
    taskHistory.value = (res.data?.tasks || (res as any).tasks || []) as BacktestTaskListItem[]

    const shouldAutoResumeRunningTask =
      autoResumeRunning &&
      !route.query.task_id &&
      !currentTaskId.value &&
      !runningTaskStatus.value &&
      !backtestResult.value &&
      !failedErrorMsg.value

    // 仅在页面没有明确展示任何任务时，才自动恢复运行中的任务
    const running = shouldAutoResumeRunningTask
      ? taskHistory.value.find(t => t.status === 'running' || t.status === 'pending')
      : null

    if (running) {
      currentTaskId.value = running.task_id
      backtestResult.value = null
      failedErrorMsg.value = null
      startPolling(running.task_id)
    }
  } catch (e) {
    console.error('获取历史任务失败', e)
  } finally {
    loadingHistory.value = false
  }
}

async function selectTask(task: BacktestTaskListItem) {
  stopPolling()
  currentTaskId.value = task.task_id

  if (task.status === 'completed') {
    runningTaskStatus.value = null
    failedErrorMsg.value = null
    await loadResult(task.task_id)
  } else if (task.status === 'running' || task.status === 'pending') {
    backtestResult.value = null
    failedErrorMsg.value = null
    runningTaskStatus.value = null
    startPolling(task.task_id)
  } else if (task.status === 'failed') {
    backtestResult.value = null
    failedErrorMsg.value = task.error_message || '回测失败'
    runningTaskStatus.value = null
  }
}

function renderChart() {
  if (!chartRef.value || !backtestResult.value) return

  // 动态加载 echarts（如项目已安装则直接 import）
  // @ts-ignore
  import('echarts').then(echarts => {
    if (!chartRef.value) return
    if (chartInstance) chartInstance.dispose()
    chartInstance = echarts.init(chartRef.value)

    const equity = backtestResult.value!.daily_equity
    const dates = equity.map(d => d.date)
    const strategyData = equity.map(d => +(d.equity_ratio * 100).toFixed(4))
    const benchmarkData = equity.map(d => +(d.benchmark_ratio * 100).toFixed(4))

    chartInstance.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', formatter: (params: any[]) => {
        return `<div>${params[0]?.axisValue}</div>` +
          params.map(p => `<div style="color:${p.color}">${p.seriesName}: ${p.value?.toFixed(2)}%</div>`).join('')
      }},
      legend: { data: ['策略净值', '上证指数'] },
      xAxis: {
        type: 'category', data: dates,
        axisLabel: { rotate: 30, fontSize: 11 }
      },
      yAxis: {
        type: 'value',
        name: '净值（初始=100%）',
        axisLabel: { formatter: '{value}%' }
      },
      series: [
        {
          name: '策略净值',
          type: 'line',
          data: strategyData,
          smooth: true,
          lineStyle: { width: 2, color: '#6366f1' },
          areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: 'rgba(99,102,241,0.35)' }, { offset: 1, color: 'rgba(99,102,241,0.02)' }] } },
          symbol: 'none'
        },
        {
          name: '上证指数',
          type: 'line',
          data: benchmarkData,
          smooth: true,
          lineStyle: { width: 2, color: '#f59e0b', type: 'dashed' },
          symbol: 'none'
        }
      ],
      grid: { left: '5%', right: '3%', bottom: '15%', containLabel: true }
    })
  }).catch(() => {
    console.warn('echarts 未安装，无法渲染图表')
  })
}

onMounted(async () => {
  const taskIdFromQuery = route.query.task_id as string | undefined

  // 恢复历史记录
  await Promise.all([
    loadTaskHistory({ autoResumeRunning: !taskIdFromQuery }),
    initializeModelSettings()
  ])
  window.addEventListener('resize', () => chartInstance?.resize())

  // 如果路由带 task_id（来自任务中心的“查看结果”跳转）,自动加载该任务
  if (taskIdFromQuery) {
    const matched = taskHistory.value.find(t => t.task_id === taskIdFromQuery)
    if (matched) {
      await selectTask(matched)
    } else {
      // 任务列表中不在（比如平常加载不到），直接尝试加载结果
      currentTaskId.value = taskIdFromQuery
      const status = await backtestApi.getTaskStatus(taskIdFromQuery).catch(() => null)
      const s = (status as any)?.data?.status || (status as any)?.status
      if (s === 'completed') {
        await loadResult(taskIdFromQuery)
      } else if (s === 'running' || s === 'pending') {
        runningTaskStatus.value = (status as any)?.data || (status as any) 
        startPolling(taskIdFromQuery)
      } else if (s === 'failed') {
        failedErrorMsg.value = (status as any)?.data?.error_message || '回测失败'
      }
    }
    // 清除 query 参数，避免刻新页面时重复加载
    router.replace({ path: '/backtest' })
  }
})

onUnmounted(() => {
  stopPolling()
  chartInstance?.dispose()
})
</script>

<style lang="scss" scoped>
.backtest-view {
  padding: 0;
}

.page-header {
  margin-bottom: 24px;

  .page-title {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 22px;
    font-weight: 700;
    color: var(--el-text-color-primary);
    margin: 0 0 6px;

    .title-icon {
      font-size: 26px;
      color: var(--el-color-primary);
    }
  }

  .page-subtitle {
    color: var(--el-text-color-secondary);
    margin: 0;
    font-size: 14px;
  }
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;

  .refresh-btn {
    margin-left: auto;
  }
}

.config-form {
  .stock-name-hint {
    margin-top: 4px;
  }

  .slider-row {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;

    .slider-label {
      width: 48px;
      text-align: right;
      font-weight: 600;
      color: var(--el-color-primary);
    }
  }

  .cost-alert {
    margin-bottom: 16px;
  }

  .model-option {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  .model-option-name {
    flex: 1;
  }

  .model-option-provider {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .model-hint {
    margin-top: 6px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    line-height: 1.5;
  }

  .submit-btn {
    width: 100%;
    height: 42px;
    font-size: 15px;
    font-weight: 600;
    border-radius: 8px;
  }
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 350px;
  overflow-y: auto;
}

.history-item {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }

  &.active {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-8);
  }

  .history-item-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }

  .history-symbol {
    font-weight: 600;
    font-size: 15px;
  }

  .history-item-meta {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .history-item-return {
    font-size: 18px;
    font-weight: 700;
    margin-top: 4px;

    &.positive { color: #ef4444; }
    &.negative { color: #22c55e; }
  }
}

.progress-card {
  margin-bottom: 16px;

  .spin-icon {
    animation: spin 1.5s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .main-progress {
    margin: 12px 0;
  }

  .progress-detail {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    margin-bottom: 4px;
  }

  .progress-step {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

.metrics-row {
  margin-bottom: 12px;
}

.metric-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 14px;
  text-align: center;
  transition: transform 0.2s;

  &:hover { transform: translateY(-2px); }

  &.positive { border-color: rgba(239, 68, 68, 0.3); background: rgba(239, 68, 68, 0.03); }
  &.negative { border-color: rgba(34, 197, 94, 0.3); background: rgba(34, 197, 94, 0.03); }
  &.neutral { border-color: var(--el-border-color-lighter); }

  .metric-label {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-bottom: 6px;
  }

  .metric-value {
    font-size: 20px;
    font-weight: 700;
    color: var(--el-text-color-primary);

    &.positive { color: #ef4444; }
    &.negative { color: #22c55e; }
  }
}

.equity-chart {
  height: 320px;
  width: 100%;
}

.empty-card {
  :deep(.el-empty) {
    padding: 60px 0;
  }
}

.error-card {
  margin-bottom: 16px;
}
</style>
