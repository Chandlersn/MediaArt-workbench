<template>
  <div class="guide-page">
    <div class="page-header">
      <h2>使用说明</h2>
      <p class="page-desc">快速了解工作台各模块的功能和操作方式</p>
    </div>

    <div class="guide-nav">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="guide-nav-btn"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        <span class="guide-nav-icon">{{ tab.icon }}</span>
        <span class="guide-nav-label">{{ tab.label }}</span>
      </button>
    </div>

    <div class="guide-body">
      <template v-if="activeTab === 'overview'">
        <div class="overview-hero">
          <div class="overview-hero-icon">📋</div>
          <div class="overview-hero-text">
            <h3>媒体艺术智能工作台</h3>
            <p>专为艺术展演组织者打造的全流程管理平台，覆盖从策划到归档的完整工作链路。</p>
          </div>
        </div>

        <div class="module-grid">
          <div v-for="m in modules" :key="m.name" class="module-card" @click="activeTab = m.tab">
            <div class="module-icon" :style="{ background: m.color }">{{ m.icon }}</div>
            <div class="module-info">
              <div class="module-name">{{ m.name }}</div>
              <div class="module-desc">{{ m.desc }}</div>
            </div>
            <span class="module-arrow">→</span>
          </div>
        </div>

        <div class="quick-start">
          <h3>🚀 快速上手</h3>
          <div class="steps-row">
            <div class="step-item">
              <div class="step-num">1</div>
              <div class="step-label">创建项目</div>
              <div class="step-detail">进入项目管理，点击新建</div>
            </div>
            <div class="step-arrow">→</div>
            <div class="step-item">
              <div class="step-num">2</div>
              <div class="step-label">添加机构</div>
              <div class="step-detail">录入合作机构信息</div>
            </div>
            <div class="step-arrow">→</div>
            <div class="step-item">
              <div class="step-num">3</div>
              <div class="step-label">录入选手</div>
              <div class="step-detail">手动添加或批量导入</div>
            </div>
            <div class="step-arrow">→</div>
            <div class="step-item">
              <div class="step-num">4</div>
              <div class="step-label">上传资料</div>
              <div class="step-detail">按阶段上传选手资料</div>
            </div>
          </div>
        </div>
      </template>

      <template v-if="activeTab === 'project'">
        <div class="section-header">
          <span class="section-icon" style="background: #3b82f6;">📁</span>
          <h3>项目管理</h3>
        </div>

        <div class="feature-cards">
          <div class="feature-card">
            <div class="feature-title">📋 项目列表</div>
            <div class="feature-desc">查看所有项目，支持按状态筛选和关键词搜索</div>
            <div class="feature-tip">
              <span class="tip-icon">💡</span>
              <span>点击项目卡片进入详情页</span>
            </div>
          </div>
          <div class="feature-card">
            <div class="feature-title">➕ 新建项目</div>
            <div class="feature-desc">填写项目名称、类型、状态、负责人、日期等信息</div>
            <div class="feature-tip">
              <span class="tip-icon">💡</span>
              <span>项目状态可在详情页随时更新</span>
            </div>
          </div>
          <div class="feature-card">
            <div class="feature-title">📎 资料管理</div>
            <div class="feature-desc">在项目详情页上传、预览、打开和删除资料文件</div>
            <div class="feature-tip">
              <span class="tip-icon">💡</span>
              <span>上传的资料会自动归档到对应目录</span>
            </div>
          </div>
        </div>

        <div class="workflow">
          <h4>操作流程</h4>
          <div class="workflow-steps">
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">新建项目</div>
                <div class="wf-step-desc">项目管理 → 点击「新建项目」→ 填写信息 → 保存</div>
              </div>
            </div>
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">关联机构</div>
                <div class="wf-step-desc">项目详情页 → 关联机构区域 → 搜索并添加机构</div>
              </div>
            </div>
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">上传资料</div>
                <div class="wf-step-desc">项目详情页 → 资料管理 → 选择类型 → 上传文件</div>
              </div>
            </div>
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">更新状态</div>
                <div class="wf-step-desc">项目详情页 → 编辑 → 修改状态（筹备中/进行中/已完成/已归档）</div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-if="activeTab === 'player'">
        <div class="section-header">
          <span class="section-icon" style="background: #10b981;">👤</span>
          <h3>选手管理</h3>
        </div>

        <div class="feature-cards">
          <div class="feature-card">
            <div class="feature-title">🔍 资料完整性检测</div>
            <div class="feature-desc">系统自动检测每位选手的资料是否齐全，缺资料的选手自动排在列表最前面</div>
            <div class="feature-tip highlight">
              <span class="tip-icon">⚠️</span>
              <span>红色标记 = 缺少必填资料，需尽快补充</span>
            </div>
          </div>
          <div class="feature-card">
            <div class="feature-title">📊 阶段资料管理</div>
            <div class="feature-desc">按赛事阶段（初赛、市赛、省赛等）分别上传和管理资料</div>
            <div class="feature-tip">
              <span class="tip-icon">💡</span>
              <span>选手晋级后，新阶段会自动出现</span>
            </div>
          </div>
          <div class="feature-card">
            <div class="feature-title">📥 批量导入</div>
            <div class="feature-desc">下载模板 → 填写数据 → 上传导入，快速录入大量选手</div>
            <div class="feature-tip">
              <span class="tip-icon">💡</span>
              <span>导入前请确保模板字段完整，避免导入失败</span>
            </div>
          </div>
        </div>

        <div class="workflow">
          <h4>操作流程</h4>
          <div class="workflow-steps">
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">添加选手</div>
                <div class="wf-step-desc">选手管理 → 新建选手 / 批量导入</div>
              </div>
            </div>
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">上传资料</div>
                <div class="wf-step-desc">选手详情 → 选择阶段 → 上传对应资料文件</div>
              </div>
            </div>
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">检查完整性</div>
                <div class="wf-step-desc">选手列表页查看红色标记，及时催收缺失资料</div>
              </div>
            </div>
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">选手晋级</div>
                <div class="wf-step-desc">选手详情 → 晋级到下一阶段 → 上传新阶段资料</div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-if="activeTab === 'organization'">
        <div class="section-header">
          <span class="section-icon" style="background: #8b5cf6;">🏢</span>
          <h3>机构管理</h3>
        </div>

        <div class="feature-cards">
          <div class="feature-card">
            <div class="feature-title">🏢 机构信息</div>
            <div class="feature-desc">管理合作机构名称、类型、级别、联系人、联系方式等</div>
          </div>
          <div class="feature-card">
            <div class="feature-title">🔗 关联项目</div>
            <div class="feature-desc">机构详情页直接展示关联项目，点击项目名即可跳转</div>
            <div class="feature-tip">
              <span class="tip-icon">💡</span>
              <span>也可以在项目详情页反向关联机构</span>
            </div>
          </div>
          <div class="feature-card">
            <div class="feature-title">⭐ 合作等级</div>
            <div class="feature-desc">支持战略合作伙伴、重要合作伙伴、普通合作伙伴三个等级</div>
          </div>
        </div>
      </template>

      <template v-if="activeTab === 'finance'">
        <div class="section-header">
          <span class="section-icon" style="background: #f59e0b;">💰</span>
          <h3>财务管理</h3>
        </div>

        <div class="feature-cards">
          <div class="feature-card">
            <div class="feature-title">📝 收支记录</div>
            <div class="feature-desc">记录每笔收入和支出，支持分类、备注、关联项目和机构</div>
          </div>
          <div class="feature-card">
            <div class="feature-title">📈 统计图表</div>
            <div class="feature-desc">收支趋势图、分类占比图，直观展示财务状况</div>
          </div>
          <div class="feature-card">
            <div class="feature-title">🔍 筛选查询</div>
            <div class="feature-desc">按类型、机构、项目、月份筛选，快速定位特定记录</div>
          </div>
          <div class="feature-card">
            <div class="feature-title">📤 导出报表</div>
            <div class="feature-desc">导出财务数据为 Excel 格式，方便汇报和存档</div>
          </div>
        </div>
      </template>

      <template v-if="activeTab === 'archive'">
        <div class="section-header">
          <span class="section-icon" style="background: #06b6d4;">🗄️</span>
          <h3>归档管理</h3>
        </div>

        <div class="feature-cards">
          <div class="feature-card">
            <div class="feature-title">📂 分类浏览</div>
            <div class="feature-desc">按项目资料、选手档案、合作机构、财务管理等分类浏览归档文件</div>
          </div>
          <div class="feature-card">
            <div class="feature-title">🖥️ 本地图标</div>
            <div class="feature-desc">文件图标使用你电脑本地的真实图标，和打开文件夹体验一致</div>
            <div class="feature-tip highlight">
              <span class="tip-icon">✨</span>
              <span>Word显示Word图标，PDF显示PDF图标</span>
            </div>
          </div>
          <div class="feature-card">
            <div class="feature-title">📤 上传与新建</div>
            <div class="feature-desc">支持上传文件到指定目录、新建文件夹</div>
          </div>
        </div>

        <div class="workflow">
          <h4>操作流程</h4>
          <div class="workflow-steps">
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">进入分类</div>
                <div class="wf-step-desc">点击分类卡片进入对应目录</div>
              </div>
            </div>
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">浏览文件</div>
                <div class="wf-step-desc">点击文件夹进入子目录，点击文件用本地软件打开</div>
              </div>
            </div>
            <div class="wf-step">
              <div class="wf-step-dot"></div>
              <div class="wf-step-content">
                <div class="wf-step-title">管理文件</div>
                <div class="wf-step-desc">悬停文件/文件夹显示操作按钮：打开、重命名、删除</div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-if="activeTab === 'other'">
        <div class="section-header">
          <span class="section-icon" style="background: #ec4899;">📦</span>
          <h3>更多模块</h3>
        </div>

        <div class="feature-cards">
          <div class="feature-card">
            <div class="feature-title">📚 知识库</div>
            <div class="feature-desc">管理解决方案、最佳实践、培训资料，团队经验不再只存在于某人的脑子里</div>
          </div>
          <div class="feature-card">
            <div class="feature-title">🖼️ 素材库</div>
            <div class="feature-desc">上传和管理图片、视频、文档等各类素材文件，图片自动显示缩略图</div>
          </div>
          <div class="feature-card">
            <div class="feature-title">📝 模板管理</div>
            <div class="feature-desc">维护合同、表单等常用模板，快速复用</div>
          </div>
          <div class="feature-card">
            <div class="feature-title">⚙️ 资料配置</div>
            <div class="feature-desc">定义资料类型和各阶段所需资料，设置必填项，上传时自动归档</div>
          </div>
          <div class="feature-card">
            <div class="feature-title">✅ 检查清单</div>
            <div class="feature-desc">项目启动/执行/收尾阶段的检查事项，含易漏事项提醒，可自定义添加</div>
          </div>
          <div class="feature-card">
            <div class="feature-title">👥 用户权限</div>
            <div class="feature-desc">管理员/编辑者/查看者三种角色，各司其职</div>
            <div class="feature-tip">
              <span class="tip-icon">💡</span>
              <span>仅管理员可管理用户账号</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const activeTab = ref('overview')

const tabs = [
  { id: 'overview', icon: '🏠', label: '总览' },
  { id: 'project', icon: '📁', label: '项目' },
  { id: 'player', icon: '👤', label: '选手' },
  { id: 'organization', icon: '🏢', label: '机构' },
  { id: 'finance', icon: '💰', label: '财务' },
  { id: 'archive', icon: '🗄️', label: '归档' },
  { id: 'other', icon: '📦', label: '更多' }
]

const modules = [
  { name: '项目管理', icon: '📁', color: '#3b82f6', desc: '创建和跟踪项目，管理项目资料', tab: 'project' },
  { name: '选手管理', icon: '👤', color: '#10b981', desc: '选手信息、资料检测、批量导入', tab: 'player' },
  { name: '机构管理', icon: '🏢', color: '#8b5cf6', desc: '合作机构信息与项目关联', tab: 'organization' },
  { name: '财务管理', icon: '💰', color: '#f59e0b', desc: '收支记录、统计图表、导出报表', tab: 'finance' },
  { name: '归档管理', icon: '🗄️', color: '#06b6d4', desc: '文件归档、分类浏览、本地图标', tab: 'archive' },
  { name: '更多模块', icon: '📦', color: '#ec4899', desc: '知识库、素材库、模板、检查清单等', tab: 'other' }
]
</script>

<style scoped>
.guide-page {
  padding: 0;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.page-desc {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: 6px;
}

.guide-nav {
  display: flex;
  gap: 6px;
  margin-bottom: 24px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.guide-nav-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.guide-nav-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.guide-nav-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.guide-nav-icon {
  font-size: 15px;
}

.guide-nav-label {
  font-weight: 500;
}

.guide-body {
  min-height: 400px;
}

.overview-hero {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 28px 32px;
  background: linear-gradient(135deg, var(--accent-light) 0%, var(--surface) 100%);
  border-radius: 12px;
  margin-bottom: 24px;
}

.overview-hero-icon {
  font-size: 48px;
  flex-shrink: 0;
}

.overview-hero-text h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px;
}

.overview-hero-text p {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.6;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-bottom: 28px;
}

.module-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  background: var(--surface);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s;
}

.module-card:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.module-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.module-info {
  flex: 1;
  min-width: 0;
}

.module-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.module-desc {
  font-size: 12px;
  color: var(--text-secondary);
}

.module-arrow {
  color: var(--text-tertiary);
  font-size: 14px;
  flex-shrink: 0;
}

.module-card:hover .module-arrow {
  color: var(--accent);
}

.quick-start {
  background: var(--surface);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  padding: 24px;
}

.quick-start h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 20px;
}

.steps-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.step-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-width: 100px;
}

.step-num {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--accent);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
}

.step-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.step-detail {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
}

.step-arrow {
  color: var(--text-tertiary);
  font-size: 18px;
  margin-bottom: 30px;
}

.section-header {
  display: flex;
  align-items: center;
  /* ⚠️ 必须显式声明：全局 style.css 的 .section-header 是 space-between，
     本组件 scoped 规则若不覆盖，图标与标题会被拉到两端。这里要让标题紧贴图标靠左。 */
  justify-content: flex-start;
  gap: 12px;
  margin-bottom: 20px;
}

.section-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.section-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.feature-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}

.feature-card {
  padding: 18px 20px;
  background: var(--surface);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  transition: all 0.15s;
}

.feature-card:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.feature-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.feature-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 10px;
}

.feature-tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.feature-tip.highlight {
  background: var(--accent-light, #eff6ff);
  color: var(--accent);
}

.tip-icon {
  flex-shrink: 0;
  font-size: 13px;
}

.workflow {
  background: var(--surface);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 20px 24px;
}

.workflow h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.workflow-steps {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.wf-step {
  display: flex;
  gap: 14px;
  position: relative;
  padding-bottom: 20px;
}

.wf-step:last-child {
  padding-bottom: 0;
}

.wf-step-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
  margin-top: 4px;
  position: relative;
}

.wf-step:not(:last-child) .wf-step-dot::after {
  content: '';
  position: absolute;
  top: 14px;
  left: 50%;
  transform: translateX(-50%);
  width: 2px;
  height: calc(100% + 8px);
  background: var(--border);
}

.wf-step-content {
  flex: 1;
}

.wf-step-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.wf-step-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}
</style>
