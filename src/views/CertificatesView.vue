<template>
  <div
    class="certificates-page"
    :class="{ 'is-dragging': isFileDragOver }"
    @dragenter.prevent="onPageDragEnter"
    @dragover.prevent="onPageDragOver"
    @dragleave.prevent="onPageDragLeave"
    @drop.prevent="onPageDrop"
  >
    <div v-if="isFileDragOver" class="page-drop-mask">松开鼠标即可导入台账（支持 .xlsx / .xls）</div>
    <div class="page-header">
      <h2>证书管理</h2>
      <div class="header-actions">
        <CertificateActions :selected="selectedCount" :filtered="filtered.length" :total="visibleCertificates.length"
          :disabled="!!quickDraft || saving" :print-busy="openingPrint || printing"
          @sync="showSync = !showSync" @import="triggerFile" @rules="showRules = !showRules"
          @templates="router.push('/templates')" @history="router.push('/print')" @print="openPrint"
          @bulk-edit="openBulkEdit" @bulk-delete="bulkDelete"
          @export-filtered="exportLedger(filtered, '导出当前筛选结果')" @export-batch="exportLedger(visibleCertificates, '导出当前整个批次')" />
        <input ref="fileInput" type="file" accept=".xlsx,.xls" style="display: none" @change="onFileChange" />
      </div>
    </div>

    <!-- 字段完整度概览：空值在维护数据时就可见（只提示不拦截，补全后打印更完整） -->
    <div v-if="incompleteFields.length" class="completeness-bar">
      <span class="bar-label">字段完整度：</span>
      <span
        v-for="f in incompleteFields"
        :key="f.column"
        class="comp-item"
        :title="`${f.label} 还有 ${f.missing} 份未填（共 ${f.total} 份）`"
      >{{ f.label }} {{ f.total - f.missing }}/{{ f.total }}</span>
      <span class="bar-hint">— 补全后批量打印不会留空</span>
    </div>

    <!-- 自动关联：从已有选手/机构数据生成证书 -->
    <div v-if="showSync" class="panel" :inert="!!quickDraft">
      <div class="panel-title">从选手与机构数据自动生成证书（自动关联）</div>
      <div class="panel-desc">
        选择赛事项目与赛事阶段后，系统会读取已录入的「选手」「机构」数据，为每位选手自动建立一张证书，
        自动带出姓名、选送机构、组别；赛事阶段、奖项、作品名称等可在下方明细中补填。
        证书编号按规范自动生成（省赛：【川】CNRCSOV + 年份 + 四位序号；国赛：Q + 序号）。
        已关联同一选手、同一赛事阶段的证书<b>只刷新身份字段</b>，保留原批次与手工填写内容；
        只有新增证书才建立新批次，再次同步已有选手不会产生空批次。
      </div>
      <div class="panel-actions">
        <label class="field">
          赛事项目
          <CustomSelect v-model="syncProjectId" style="width: 260px">
            <option value="">（不限项目，按全部选手）</option>
            <option v-for="p in projectOptions" :key="p.id" :value="p.id">{{ p.name }}</option>
          </CustomSelect>
        </label>
        <label class="field">
          赛事阶段
          <CustomSelect v-model="syncRound" style="width: 160px">
            <option v-for="r in ROUND_ORDER" :key="r" :value="r">{{ r }}</option>
          </CustomSelect>
        </label>
        <button class="btn-primary" :disabled="syncing" @click="runSync">
          {{ syncing ? '同步中…' : '开始同步' }}
        </button>
        <span class="muted">当前选手库共 {{ playerCount }} 人</span>
      </div>
    </div>

    <!-- 编号规则：可配置编号模板（变量化），换项目/换赛事阶段均可复用 -->
    <div v-if="showRules" class="panel" :inert="!!quickDraft">
      <div class="panel-title">证书编号规则（可复用模板）</div>
      <div class="panel-desc">
        用占位变量编排编号格式，导入或同步时按模板自动生成。可用变量：
        <code>{province}</code> 省份、<code>{code}</code> 编号前缀、<code>{year}</code> 年份、
        <code>{seq}</code> 序号、<code>{seq:N}</code> 补零到 N 位（如 <code>{seq:4}</code>）。
        省赛与国赛分别配置；下方默认值决定生成时的省份/前缀/年份。
      </div>
      <div class="rules-grid">
        <label class="field col">
          省赛模板
          <input v-model="tplProvince" class="form-input mono" placeholder="【{province}】{code}{year}{seq:4}" />
        </label>
        <label class="field col">
          国赛模板
          <input v-model="tplNational" class="form-input mono" placeholder="Q{seq}" />
        </label>
        <label class="field">
          默认省份
          <input v-model="defProvince" class="form-input" style="width:90px" placeholder="川" />
        </label>
        <label class="field">
          默认编号前缀
          <input v-model="defCode" class="form-input mono" style="width:150px" placeholder="CNRCSOV" />
        </label>
        <label class="field">
          默认年份
          <input v-model.number="defYear" type="number" class="form-input" style="width:100px" />
        </label>
      </div>
      <div class="rules-preview">
        <span class="muted">预览：</span>
        <span class="pill mono">省赛 {{ previewProvince }}</span>
        <span class="pill mono">国赛 {{ previewNational }}</span>
      </div>
      <div class="panel-actions">
        <button class="btn-primary" :disabled="savingRules" @click="saveRules">
          {{ savingRules ? '保存中…' : '保存规则' }}
        </button>
        <span class="warn-text">保存后立即生效，并随数据持久化；切换项目时直接改这里即可复用。</span>
      </div>
    </div>

    <!-- 导入预览 -->
    <div v-if="preview" class="panel" :inert="!!quickDraft">
      <div class="panel-head">
        <div>
          <strong>导入预览：{{ preview.fileName }}</strong>
          <span class="muted">（{{ preview.orgSheets }} 个机构分表，提取 {{ preview.raw }} 行）</span>
        </div>
        <button class="btn-text" @click="cancelImport">收起</button>
      </div>
      <div class="preview-stats">
        <div class="stat"><span class="num">{{ preview.unique }}</span><span class="lbl">去重后证书数</span></div>
        <div class="stat"><span class="num">{{ preview.dup }}</span><span class="lbl">重复编号（将被合并）</span></div>
        <div class="stat"><span class="num">{{ preview.missingWorkName }}</span><span class="lbl">缺作品名</span></div>
      </div>
      <div class="preview-dist">
        <div class="dist-block">
          <div class="dist-title">按奖项</div>
          <span v-for="(c, k) in preview.byAward" :key="k" class="pill">{{ k }}：{{ c }}</span>
        </div>
        <div class="dist-block">
          <div class="dist-title">按赛事阶段</div>
          <span v-for="(c, k) in preview.byRound" :key="k" class="pill">{{ k }}：{{ c }}</span>
        </div>
      </div>
      <div class="panel-actions">
        <label class="field">
          归属项目
          <CustomSelect v-model="importProjectId" style="width: 260px">
            <option value="">（未选择，仅作独立证书）</option>
            <option v-for="p in projectOptions" :key="p.id" :value="p.id">{{ p.name }}</option>
          </CustomSelect>
        </label>
        <button class="btn-primary" :disabled="importing" @click="confirmImport">
          {{ importing ? '导入中…' : '确认导入' }}
        </button>
        <span class="warn-text">导入按证书编号合并覆盖；重复编号只保留最后一条</span>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div v-if="stats.total > 0" class="stat-cards">
      <div class="stat-card"><span class="num">{{ stats.total }}</span><span class="lbl">证书总数</span></div>
      <div class="stat-card"><span class="num">{{ stats.packed }}</span><span class="lbl">已打包</span></div>
      <div class="stat-card"><span class="num">{{ stats.unpacked }}</span><span class="lbl">未打包</span></div>
      <div class="stat-card"><span class="num">{{ stats.missingWorkName }}</span><span class="lbl">缺作品名</span></div>
    </div>

    <!-- 导入或同步新增证书形成批次；切换批次仅改变本标签页的查看范围 -->
    <div v-if="sessions.length > 0" class="session-bar">
      <span class="session-label">证书批次</span>
      <div class="session-chips">
        <button
          v-for="s in sessions"
          :key="s.id"
          class="session-chip"
          :class="{ active: s.id === activeSessionId }"
          :disabled="!!quickDraft"
          @click="switchSession(s.id)"
        >
          <span class="session-name">{{ s.name }}</span>
          <span class="session-count">{{ s.count }}</span>
          <span
            class="session-del"
            :title="s.id === 'legacy-import' ? '删除将抹除全部历史导入数据' : '删除该批次（仅抹除本批）'"
            @click.stop="removeSession(s)"
          >×</span>
        </button>
      </div>
    </div>

    <!-- 来源上下文：从机构 / 项目详情页的「关联证书」跳转带入 -->
    <div v-if="ctxActive" class="ctx-bar">
      <span class="ctx-label">已限定来源：{{ ctxLabel }}</span>
      <button class="btn-text" :disabled="!!quickDraft" @click="clearContext">清除筛选</button>
    </div>

    <!-- 筛选栏 -->
    <div v-if="visibleCertificates.length > 0" class="filter-bar">
      <CustomSelect v-model="filterAward" :disabled="!!quickDraft" style="width:150px">
        <option value="">全部奖项</option>
        <option v-for="a in awardOptions" :key="a" :value="a">{{ a }}</option>
      </CustomSelect>
      <CustomSelect v-model="filterRound" :disabled="!!quickDraft" style="width:150px">
        <option value="">全部阶段</option>
        <option v-for="r in roundOptions" :key="r" :value="r">{{ r }}</option>
      </CustomSelect>
      <CustomSelect v-model="filterPacked" :disabled="!!quickDraft" style="width:150px">
        <option value="">全部打包状态</option>
        <option value="已打包">已打包</option>
        <option value="未打包">未打包</option>
        <option value="待核对">待核对</option>
      </CustomSelect>
      <button class="btn-secondary btn-sm" :disabled="!!quickDraft" :class="{ active: ctxMissing }" @click="ctxMissing = !ctxMissing">
        仅缺作品名
      </button>
      <input v-model="keyword" :disabled="!!quickDraft" class="form-input" placeholder="搜索姓名 / 机构 / 作品 / 证书号" style="flex:1; min-width:180px;" />
    </div>

    <!-- 图表 -->
    <div v-if="stats.total > 0" class="charts">
      <div class="chart-card">
        <div class="chart-title">奖项分布</div>
        <canvas ref="awardChart"></canvas>
      </div>
      <div class="chart-card">
        <div class="chart-title">按机构 TOP 10</div>
        <canvas ref="orgChart"></canvas>
      </div>
    </div>

    <!-- 明细表 -->
    <div v-if="filtered.length" class="ledger-toolbar">
      <span>当前 {{ filtered.length }} 份<span v-if="selectedCount"> · 已选 {{ selectedCount }} 份</span></span>
      <span v-if="canEditCertificates" class="muted">{{ quickDraft ? 'Enter 保存并填写下一条 · Esc 取消当前修改' : '点击作品名称或指导老师可快速补录' }}</span>
    </div>
    <div v-if="filtered.length > 0" ref="quickTable" class="cert-table-wrap">
      <table class="cert-table">
        <thead>
          <tr>
            <th class="sel-col"><input type="checkbox" :checked="allPagedSelected" title="全选本页" @change="toggleSelectPage" /></th>
            <th>证书编号</th>
            <th>选手姓名</th>
            <th>组别</th>
            <th>奖项</th>
            <th>赛事阶段</th>
            <th>作品名称</th>
            <th>指导老师</th>
            <th>选送机构</th>
            <th>收件机构</th>
            <th>打包</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in pagedRows" :key="certKey(c)">
            <td class="sel-col"><input type="checkbox" :checked="selectedKeys.has(certKey(c))" @change="toggleSelect(c)" /></td>
            <td class="mono">{{ c.certNumber }}</td>
            <td>{{ c.playerName }}</td>
            <td>{{ c.groupName }}</td>
            <td><span :class="['badge', awardClass(c.award)]">{{ c.award || '待填' }}</span></td>
            <td>{{ c.certRound }}</td>
            <td v-for="field in quickFields" :key="field.column" class="quick-cell" :class="{ 'cell-warn': !c[field.column] }">
              <div v-if="isQuickEditing(c, field.column)" class="quick-editor">
                <input v-model="quickDraft.value" class="form-input quick-input" :aria-label="`${c.playerName}的${field.label}`" :disabled="quickBusy"
                  @keydown.enter="!$event.isComposing && saveQuickEdit(true)" @keydown.esc.prevent="cancelQuickEdit" />
                <div class="quick-controls">
                  <button class="btn-text" :disabled="quickBusy" @click="saveQuickEdit(false)">{{ quickBusy ? '保存中…' : '保存' }}</button>
                  <button class="btn-text" :disabled="quickBusy" @click="cancelQuickEdit">取消</button>
                </div>
                <span v-if="quickError" class="quick-error" role="alert">{{ quickError }}</span>
              </div>
              <button v-else-if="canEditCertificates" class="quick-value" :disabled="!!quickDraft || saving"
                :aria-label="`填写${c.playerName}的${field.label}`" @click="beginQuickEdit(c, field.column)">{{ c[field.column] || '点击补录' }} <span aria-hidden="true">✎</span></button>
              <span v-else>{{ c[field.column] || '待补录' }}</span>
            </td>
            <td>{{ c.orgName }}</td>
            <td>{{ c.receivingOrg || c.orgName }}</td>
            <td>
              <CustomSelect v-model="c.packed" :disabled="!!quickDraft || !canEditCertificates" style="width:110px" @change="() => setPacked(c)">
                <option value="已打包">已打包</option>
                <option value="未打包">未打包</option>
                <option value="待核对">待核对</option>
              </CustomSelect>
            </td>
            <td>
              <div class="row-actions">
                <span
                  v-if="printHist(c)"
                  class="print-hist"
                  :title="`最近打印：${printHist(c).last}（${printHist(c).title}）`"
                >打印 {{ printHist(c).count }} 次</span>
                <span
                  v-if="legacyPrintHist(c)"
                  class="print-hist"
                  :title="`历史记录未保存批次；最近打印：${legacyPrintHist(c).last}（${legacyPrintHist(c).title}）`"
                >历史 {{ legacyPrintHist(c).count }} 次（批次未记录）</span>
                <button class="btn-text" :disabled="!canEditCertificates || saving || !!quickDraft" @click="openEdit(c)">填写</button>
                <span class="row-sep"></span>
                <button class="btn-text danger" :disabled="!!quickDraft" @click="removeCert(c)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="table-foot" :inert="!!quickDraft">
        <Pagination
          :total-items="filtered.length"
          :page-size="pageSize"
          :current-page="currentPage"
          @page-change="currentPage = $event"
          @page-size-change="onPageSizeChange"
        />
      </div>
    </div>

    <div v-if="certificates.length === 0" class="empty-state">
      暂无证书数据。可点击右上角「导入台账」导入既有 Excel，或用「从选手同步」由系统中已录入的选手自动生成。
    </div>
    <div v-else-if="visibleCertificates.length === 0" class="empty-state">
      当前批次暂无证书。可在上方「证书批次」中切换到其他批次，或导入新的台账 / 从选手同步。
    </div>
    <div v-else-if="filtered.length === 0" class="empty-state">当前筛选下暂无证书，可调整筛选条件继续查看。</div>

    <!-- 批量打印弹窗 -->
    <div v-if="showPrint" class="drawer-mask" @click.self="closePrint">
      <div class="print-modal" role="dialog" aria-modal="true" aria-label="批量打印证书">
        <div class="drawer-head">
          <strong>批量打印证书（已选 {{ printReferences.length }} 份）</strong>
          <button class="btn-text" :disabled="printing || saving" @click="closePrint">关闭</button>
        </div>
        <div class="print-workspace">
        <div class="drawer-body print-settings">
          <div v-if="printTemplates.length === 0" class="muted">
            还没有打印模板。请先到左侧导航「模板管理」上传底图、勾选字段创建模板。
          </div>
          <template v-else>
            <div class="drawer-row">
              <span class="drawer-label">打印模板</span>
              <CustomSelect v-model="printTplId" :disabled="printing || saving" style="width: 100%">
                <option v-for="t in printTemplates" :key="t.id" :value="t.id">
                  {{ t.name }}（{{ (t.fields || []).length }} 个字段）
                </option>
              </CustomSelect>
            </div>
            <div class="drawer-row">
              <span class="drawer-label">已选证书</span>
              <div class="print-sel-list">
                <span v-for="c in printRecords.slice(0, 20)" :key="certKey(c)" class="pill mono">{{ c.certNumber }} {{ c.playerName }}</span>
                <span v-if="printReferences.length > 20" class="muted">…等 {{ printReferences.length }} 份</span>
              </div>
            </div>
            <section class="print-preflight" aria-live="polite" :aria-busy="checkingPrint">
              <div class="print-preflight-head">
                <strong>打印前检查</strong>
                <button class="btn-text" :disabled="checkingPrint || printing || saving" @click="checkPrint">重新检查</button>
              </div>
              <p v-if="checkingPrint" class="muted">正在检查本次 {{ printReferences.length }} 份证书…</p>
              <p v-else-if="printCheckError" class="print-check-error">检查失败：{{ printCheckError }}。请重新检查后再生成。</p>
              <template v-else-if="printCheck">
                <p v-if="!printIssueCount" class="print-check-ok">检查通过，未发现打印字段问题。</p>
                <p v-else class="muted">
                  本次发现 {{ printIssueCount }} 项问题。
                  {{ printCheck.canGenerate ? '可去填写修正；若确认保留，可选择“仍要生成并打印”。' : '模板存在错误，请修正或更换模板后重新检查。' }}
                </p>
                <div v-for="(issue, index) in printCheck.issues" :key="index" class="print-issue" :class="{ 'print-issue-error': issue.severity === 'error' }">
                  <div class="print-issue-detail">
                    <strong>{{ issue.reference ? `${issue.reference.certNumber} ${issue.playerName || ''}` : '打印模板' }} · {{ issue.label || '版面' }}</strong>
                    <span>{{ issue.message }}</span>
                    <span v-if="issue.value !== null && issue.value !== undefined && String(issue.value).trim()" class="muted">当前值：{{ issue.value }}</span>
                  </div>
                  <button v-if="canFillPrintIssue(issue)" class="btn-secondary btn-sm" :disabled="!canEditCertificates || saving || printing || checkingPrint" @click="fillPrintIssue(issue)">去填写</button>
                </div>
                <p v-if="printCheck.truncated" class="muted">仅显示前 {{ printCheck.issues.length }} 项，其他问题尚未展开；修正后请重新检查。</p>
                <p v-if="printIssueCount && !canEditCertificates" class="muted">当前账户可查看检查结果；补录需要证书修改权限。</p>
              </template>
              <p v-else class="muted">等待检查。</p>
              <p v-if="printAttemptError" class="print-check-error">{{ printAttemptError }}</p>
            </section>
            <div v-if="printWarnings.length" class="print-warn">
              <div class="side-title">部分字段取值为空，请确认：</div>
              <div v-for="w in printWarnings" :key="w.column" class="muted">
                {{ w.label }}：{{ w.count }} 份为空
              </div>
            </div>
            <div class="muted">生成后自动打开打印预览窗口，请在打印对话框中选择「缩放 100%」并关闭页眉页脚。</div>
          </template>
        </div>
        <CertificatePrintPreview :template-id="printTplId" :references="printReferences" :check="printCheck" :disabled="printing || checkingPrint"
          @ready="onPrintPreviewReady" @recheck="checkPrint" />
        </div>
        <div class="drawer-foot print-footer">
          <span class="muted">本次 {{ printReferences.length }} 份 · 确认预览后生成打印件</span>
          <button class="btn-primary" :disabled="printing || saving || checkingPrint || !printReady || printPreviewToken !== printCheck?.validationToken" @click="runPrint">
            {{ printing ? '生成中…' : checkingPrint ? '检查中…' : printIssueCount && printCheck?.canGenerate ? '仍要生成并打印' : '生成并打印' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 填写抽屉 -->
    <div v-if="editing" class="drawer-mask" @click.self="closeEdit">
      <div ref="editDrawer" class="drawer">
        <div class="drawer-head">
          <strong>填写证书信息</strong>
          <button class="btn-text" :disabled="saving" :title="editFromPrint ? '取消补录并返回打印检查' : '收起填写窗口'" @click="closeEdit">收起</button>
        </div>
        <div class="drawer-body">
          <div class="drawer-row">
            <span class="drawer-label">证书编号</span>
            <span class="mono">{{ editing.certNumber }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">选手姓名</span>
            <input v-model="editing.playerName" data-cert-field="playerName" aria-label="选手姓名" :disabled="saving || !canEditCertificates" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">赛事阶段</span>
            <CustomSelect v-model="editing.certRound" data-cert-field="certRound" aria-label="赛事阶段" :disabled="saving || !canEditCertificates" style="width:100%">
              <option v-for="r in roundOptionsAll" :key="r" :value="r">{{ r }}</option>
            </CustomSelect>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">组别</span>
            <input v-model="editing.groupName" data-cert-field="groupName" aria-label="组别" :disabled="saving || !canEditCertificates" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">奖项</span>
            <CustomSelect v-model="editing.award" data-cert-field="award" aria-label="奖项" :disabled="saving || !canEditCertificates" style="width:100%">
              <option value="">（待定）</option>
              <option v-for="a in awardOptionsAll" :key="a" :value="a">{{ a }}</option>
            </CustomSelect>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">作品名称</span>
            <input v-model="editing.workName" data-cert-field="workName" aria-label="作品名称" :disabled="saving || !canEditCertificates" class="form-input" placeholder="必填，用于证书印制" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">指导老师</span>
            <input v-model="editing.instructor" data-cert-field="instructor" aria-label="指导老师" :disabled="saving || !canEditCertificates" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">语种</span>
            <input v-model="editing.language" data-cert-field="language" aria-label="语种" :disabled="saving || !canEditCertificates" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">晋级情况</span>
            <input v-model="editing.promotion" data-cert-field="promotion" aria-label="晋级情况" :disabled="saving || !canEditCertificates" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">选送机构（校区）</span>
            <input v-model="editing.orgName" data-cert-field="orgName" aria-label="选送机构（校区）" :disabled="saving || !canEditCertificates" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">收件机构</span>
            <input v-model="editing.receivingOrg" data-cert-field="receivingOrg" aria-label="收件机构" :disabled="saving || !canEditCertificates" class="form-input" placeholder="决定导出时分到哪张表" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">打包状态</span>
            <CustomSelect v-model="editing.packed" data-cert-field="packed" aria-label="打包状态" :disabled="saving || !canEditCertificates" style="width:100%">
              <option value="已打包">已打包</option>
              <option value="未打包">未打包</option>
              <option value="待核对">待核对</option>
            </CustomSelect>
          </div>
        </div>
        <div class="drawer-foot">
          <button class="btn-primary" :disabled="saving || !canEditCertificates" @click="saveEdit">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 批量修改弹窗：把同一个值写入所有勾选的证书 -->
    <div v-if="showBulkEdit" class="bulk-mask" @click.self="showBulkEdit = false">
      <div class="bulk-dialog" role="dialog" aria-modal="true" aria-label="批量修改证书">
        <header class="bulk-head">
          <strong>批量修改证书（已选 {{ selectedCount }} 份）</strong>
          <button class="bulk-x" aria-label="关闭" @click="showBulkEdit = false">×</button>
        </header>
        <div class="bulk-body">
          <div class="bulk-row">
            <span class="drawer-label">字段</span>
            <CustomSelect v-model="bulkEditField" style="width: 160px">
              <option v-for="f in BULK_EDITABLE_FIELDS" :key="f.key" :value="f.key">{{ f.label }}</option>
            </CustomSelect>
          </div>
          <div class="bulk-row">
            <span class="drawer-label">新值</span>
            <input
              v-model="bulkEditValue"
              class="bulk-input"
              :placeholder="`新的${bulkEditFieldLabel}（留空表示清空该字段）`"
              @keyup.enter="applyBulkEdit"
            />
          </div>
          <p class="bulk-hint">只影响当前批次里勾中的 {{ selectedCount }} 份，未勾选的不动。</p>
        </div>
        <footer class="bulk-foot">
          <button class="btn-secondary" @click="showBulkEdit = false">取消</button>
          <button class="btn-primary" :disabled="bulkEditBusy" @click="applyBulkEdit">
            {{ bulkEditBusy ? '应用中…' : `应用到 ${selectedCount} 份` }}
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated, watch, nextTick } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import { useCertificateStore } from '../stores/certificate'
import { useProjectStore } from '../stores/project'
import { useOrganizationStore } from '../stores/organization'
import { usePlayerStore } from '../stores/player'
import { useUserStore } from '../stores/user'
import { useCertificatePrintPreflight } from '../composables/useCertificatePrintPreflight'
import { useCertificateQuickEdit } from '../composables/useCertificateQuickEdit'
import CertificateActions from '../components/CertificateActions.vue'
import CertificatePrintPreview from '../components/CertificatePrintPreview.vue'
import { parseCertificateFile } from '../services/certificateImport'
import { exportCertificateLedger, ROUND_ORDER } from '../services/certificateExport'
import { validatePrint, generatePrint, archivePrint, openHtmlWindow, fetchPrintLogs, fetchFieldCatalog } from '../services/print'
import { indexPrintReferences, printReferenceKey } from '../utils/printReferences'
import * as dataService from '../services/dataService'
import CustomSelect from '../components/CustomSelect.vue'
import Pagination from '../components/Pagination.vue'
import Chart from 'chart.js/auto'

const { success, error: toastError, warning } = useToast()
const { confirm } = useConfirmDialog()
const certStore = useCertificateStore()
const projectStore = useProjectStore()
const orgStore = useOrganizationStore()
const playerStore = usePlayerStore()
const userStore = useUserStore()
const canEditCertificates = computed(() => userStore.can('projects', 'edit'))

const certificates = computed(() => certStore.certificates)
const visibleCertificates = computed(() => certStore.visibleCertificates)
const sessions = computed(() => certStore.sessions)
const activeSessionId = computed(() => certStore.activeSessionId)
const fileInput = ref(null)
const preview = ref(null)
const importing = ref(false)
const syncing = ref(false)
const saving = ref(false)
const importProjectId = ref('')
const showSync = ref(false)
const showRules = ref(false)
const syncProjectId = ref('')
const syncRound = ref(ROUND_ORDER[0])

// 编号规则编辑（绑定到 certSettings 的模板与默认值）
const tplProvince = ref('')
const tplNational = ref('')
const defProvince = ref('')
const defCode = ref('')
const defYear = ref(new Date().getFullYear())
const savingRules = ref(false)

const previewProvince = computed(() => {
  try { return certStore.formatCertNumber('省级展演', 1, { province: defProvince.value || '川', code: defCode.value || 'CNRCSOV', year: defYear.value || new Date().getFullYear() }) } catch (e) { return '（模板无效）' }
})
const previewNational = computed(() => {
  try { return certStore.formatCertNumber('全国展演', 1, { province: defProvince.value || '川', code: defCode.value || 'CNRCSOV', year: defYear.value || new Date().getFullYear() }) } catch (e) { return '（模板无效）' }
})

const filterAward = ref('')
const filterRound = ref('')
const filterPacked = ref('')
const keyword = ref('')

// ===== 来源上下文筛选：由机构 / 项目详情页的「关联证书」点击跳转带入 =====
const route = useRoute()
const router = useRouter()
const ctxOrgId = ref('')
const ctxOrgName = ref('')
const ctxProjectId = ref('')
const ctxMissing = ref(false)

const applyRouteQuery = () => {
  const q = route.query || {}
  ctxOrgId.value = String(q.orgId || '')
  ctxOrgName.value = String(q.orgName || '')
  ctxProjectId.value = String(q.projectId || '')
  ctxMissing.value = q.missingWorkName === '1'
  filterAward.value = String(q.award || '')
  filterRound.value = String(q.round || '')
  filterPacked.value = String(q.packed || '')
  keyword.value = String(q.keyword || '')
  currentPage.value = 1
}

const clearContext = () => {
  ctxOrgId.value = ''
  ctxOrgName.value = ''
  ctxProjectId.value = ''
  ctxMissing.value = false
  currentPage.value = 1
  // 同时清掉地址栏参数，避免刷新又回到筛选态
  if (Object.keys(route.query || {}).length) router.replace({ path: '/certificates' })
}

const currentPage = ref(1)
const pageSize = ref(50)

const awardChart = ref(null)
const orgChart = ref(null)
let chartInstances = { award: null, org: null }

const projectOptions = computed(() => (projectStore.projects || []).map(p => ({ id: p.id, name: p.name })))
const playerCount = computed(() => (playerStore.players || []).length)

const AWARD_BASE = ['特金奖', '金奖', '银奖', '铜奖', '退赛']
const awardOptionsAll = ref(AWARD_BASE.slice())
const roundOptionsAll = ref(ROUND_ORDER.slice())

const awardOptions = computed(() => {
  const set = new Set(visibleCertificates.value.map(c => c.award).filter(Boolean))
  const list = AWARD_BASE.filter(a => set.has(a)).concat([...set].filter(a => !AWARD_BASE.includes(a)))
  // 奖项为空的证书在分组里叫「未分类」，下拉也要能选到
  return visibleCertificates.value.some(c => !c.award) ? list.concat(['未分类']) : list
})
const roundOptions = computed(() => {
  const set = new Set(visibleCertificates.value.map(c => c.certRound).filter(Boolean))
  return [...new Set([...ROUND_ORDER.filter(r => set.has(r)), ...[...set].filter(r => !ROUND_ORDER.includes(r))])]
})

// 上下文是否生效 + 提示条文案
const ctxActive = computed(() => !!(ctxOrgId.value || ctxOrgName.value || ctxProjectId.value))
const ctxLabel = computed(() => {
  if (ctxProjectId.value) {
    const p = projectOptions.value.find(x => x.id === ctxProjectId.value)
    return `项目「${p?.name || ctxProjectId.value}」`
  }
  if (ctxOrgName.value || ctxOrgId.value) return `机构「${ctxOrgName.value || ctxOrgId.value}」`
  return ''
})

const stats = computed(() => certStore.getCertStats({
  award: filterAward.value,
  certRound: filterRound.value,
  packed: filterPacked.value,
  orgId: ctxOrgId.value,
  orgName: ctxOrgName.value,
  projectId: ctxProjectId.value,
  missingWorkName: ctxMissing.value
}))

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return visibleCertificates.value.filter(c => {
    // 来源上下文：机构按 id / 名称任一命中（与详情页统计口径一致）；项目按 projectId
    if (ctxOrgId.value || ctxOrgName.value) {
      const hitOrg = (ctxOrgId.value && c.orgId === ctxOrgId.value) ||
        (ctxOrgName.value && c.orgName === ctxOrgName.value)
      if (!hitOrg) return false
    }
    if (ctxProjectId.value && c.projectId !== ctxProjectId.value) return false
    if (ctxMissing.value && !c.missingWorkName) return false
    if (filterAward.value) {
      if ((c.award || '未分类') !== filterAward.value) return false
    }
    if (filterRound.value && c.certRound !== filterRound.value) return false
    if (filterPacked.value) {
      if ((c.packed || '待核对') !== filterPacked.value) return false
    }
    if (kw) {
      const hay = [c.playerName, c.orgName, c.receivingOrg, c.workName, c.certNumber, c.instructor].join(' ').toLowerCase()
      if (!hay.includes(kw)) return false
    }
    return true
  })
})

const pagedRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})

const onPageSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
}

const quickFields = [{ column: 'workName', label: '作品名称' }, { column: 'instructor', label: '指导老师' }]
const quickTable = ref(null)
const { draft: quickDraft, busy: quickBusy, error: quickError, begin: beginQuick, cancel: cancelQuickEdit, save: commitQuickEdit } = useCertificateQuickEdit({
  canEdit: () => canEditCertificates.value,
  records: () => certificates.value,
  update: (...args) => certStore.updateCert(...args)
})
const isQuickEditing = (record, column) => quickDraft.value?.column === column && certKey(quickDraft.value) === certKey(record)
const focusQuickEdit = async () => {
  if (!quickDraft.value) return
  const index = filtered.value.findIndex(record => certKey(record) === certKey(quickDraft.value))
  if (index >= 0) currentPage.value = Math.floor(index / pageSize.value) + 1
  await nextTick()
  const input = quickTable.value?.querySelector('.quick-input')
  input?.focus()
  input?.select()
}
const beginQuickEdit = async (record, column) => {
  if (beginQuick(record, column, filtered.value)) await focusQuickEdit()
}
const saveQuickEdit = async advance => {
  if (await commitQuickEdit(advance)) {
    if (quickDraft.value) await focusQuickEdit()
    else success('已保存')
  }
}
const leaveQuickEdit = async () => {
  if (quickBusy.value) { warning('正在保存，请稍候再离开'); return false }
  if (!quickDraft.value) return true
  if (quickDraft.value.value !== quickDraft.value.original) {
    const discard = await confirm({ title: '补录内容尚未保存', message: '离开会丢弃当前输入，已保存的内容不受影响。',
      confirmText: '放弃并离开', cancelText: '继续填写', type: 'default' })
    if (!discard) return false
  }
  cancelQuickEdit()
  return true
}
onBeforeRouteLeave(leaveQuickEdit)
onBeforeRouteUpdate(leaveQuickEdit)

watch([filtered], () => { if (currentPage.value > Math.max(1, Math.ceil(filtered.value.length / pageSize.value))) currentPage.value = 1 })

const awardClass = (award) => {
  if (award === '特金奖') return 'a-gold'
  if (award === '金奖') return 'a-silver'
  if (award === '银奖') return 'a-bronze'
  if (award === '铜奖') return 'a-copper'
  return 'a-other'
}

const triggerFile = () => fileInput.value?.click()
const cancelImport = () => { preview.value = null; if (fileInput.value) fileInput.value.value = '' }

/** 解析并预览导入文件（点击选择与拖拽导入共用同一逻辑） */
const importFile = async (file) => {
  if (!file) return
  try {
    const { preview: p, rows, meta } = await parseCertificateFile(file)
    preview.value = { ...p, fileName: file.name, _rows: rows, _meta: meta }
  } catch (err) {
    toastError('解析文件失败：' + (err.message || err))
  }
}

const onFileChange = (e) => importFile(e.target.files && e.target.files[0])

// ---- 拖拽导入：把 Excel 拖到页面任意处即可导入台账 ----
// 台账是本页的主体操作，用户从资源管理器直接拖文件进来最省事。
const isFileDragOver = ref(false)
let dragDepth = 0

const isExcelFile = (name) => /\.(xlsx|xls)$/i.test(name || '')

const onPageDragEnter = (e) => {
  if (!e.dataTransfer?.types?.includes('Files')) return
  dragDepth += 1
  isFileDragOver.value = true
}

const onPageDragOver = (e) => {
  if (e.dataTransfer?.types?.includes('Files')) isFileDragOver.value = true
}

const onPageDragLeave = () => {
  dragDepth -= 1
  if (dragDepth <= 0) {
    dragDepth = 0
    isFileDragOver.value = false
  }
}

const onPageDrop = (e) => {
  dragDepth = 0
  isFileDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  if (!isExcelFile(file.name)) {
    toastError('只支持 Excel 文件（.xlsx / .xls）')
    return
  }
  importFile(file)
}

const matchOrgId = (orgName) => {
  const found = (orgStore.organizations || []).find(o => o.name === orgName)
  return found ? found.id : ''
}
const matchPlayerId = (name, orgName) => {
  const list = playerStore.players || []
  const hit = list.find(p => p.name === name &&
    (p.orgName === orgName || (orgStore.organizations.find(o => o.id === p.orgId)?.name === orgName)))
  return hit ? hit.id : ''
}

const confirmImport = async () => {
  if (!preview.value) return
  importing.value = true
  try {
    const rows = preview.value._rows.map(r => ({
      ...r,
      projectId: importProjectId.value,
      orgId: matchOrgId(r.orgName),
      playerId: matchPlayerId(r.playerName, r.orgName),
      importId: preview.value._meta?.parsedAt || new Date().toISOString()
    }))
    const count = await certStore.importCertificates(rows, { fileName: preview.value.fileName, projectId: importProjectId.value })
    success(`已导入 ${count} 条证书`)
    preview.value = null
    if (fileInput.value) fileInput.value.value = ''
  } catch (err) {
    toastError('导入失败：' + (err.message || err))
  } finally {
    importing.value = false
  }
}

/** 自动关联：由选手库生成证书 */
const runSync = async () => {
  if (playerCount.value === 0) {
    warning('选手库为空，请先在「选手」中录入参赛选手')
    return
  }
  syncing.value = true
  try {
    const res = await certStore.syncFromPlayers(playerStore.players || [], orgStore.organizations || [], {
      projectId: syncProjectId.value,
      certRound: syncRound.value,
      assignNumbers: true
    })
    if (!res.created && !res.updated) warning('所选项目没有可同步的选手，证书数据未变更')
    else success(`同步完成：新增 ${res.created} 条，更新 ${res.updated} 条${res.created ? '；新增证书位于新批次，已有证书保留原批次' : '；已显示更新所在批次'}`)
    showSync.value = false
  } catch (err) {
    toastError('同步失败：' + (err.message || err))
  } finally {
    syncing.value = false
  }
}

/** 导出台账 */
const exportLedger = (list, scopeLabel) => {
  if (!list || list.length === 0) {
    warning('没有可导出的证书数据')
    return
  }
  try {
    const projectName = importProjectId.value
      ? (projectOptions.value.find(p => p.id === importProjectId.value)?.name || '')
      : ''
    const res = exportCertificateLedger(list, {
      titlePrefix: projectName || '证书台账',
      includeSummaries: true
    })
    success(`${scopeLabel}：已生成 ${res.sheetCount} 张工作表，共 ${res.certCount} 条证书`)
  } catch (err) {
    toastError('导出失败：' + (err.message || err))
  }
}

const setPacked = async (c) => {
  try {
    await certStore.updateCert(c.certNumber, { packed: c.packed }, c.sessionId)
  } catch (err) {
    toastError('更新打包状态失败：' + (err.message || err))
  }
}

// ===== 勾选 + 批量打印 =====
const certKey = (c) => printReferenceKey({ certNumber: c.certNumber, sessionId: c.sessionId || '' })
const selectedKeys = ref(new Set())
const toggleSelect = (c) => {
  const next = new Set(selectedKeys.value)
  next.has(certKey(c)) ? next.delete(certKey(c)) : next.add(certKey(c))
  selectedKeys.value = next
}
const toggleSelectPage = () => {
  const next = new Set(selectedKeys.value)
  const all = allPagedSelected.value
  pagedRows.value.forEach(c => all ? next.delete(certKey(c)) : next.add(certKey(c)))
  selectedKeys.value = next
}
const allPagedSelected = computed(() =>
  pagedRows.value.length > 0 && pagedRows.value.every(c => selectedKeys.value.has(certKey(c))))
// 勾选与筛选独立：按住的勾选集合打印，不受后续筛选影响
const selectedList = computed(() => visibleCertificates.value.filter(c => selectedKeys.value.has(certKey(c))))
const selectedCount = computed(() => selectedList.value.length)

const showPrint = ref(false)
const printTemplates = ref([])
const printTplId = ref('')
const printing = ref(false)
const openingPrint = ref(false)
const printWarnings = ref([])
const printAttemptError = ref('')
const printPreviewToken = ref('')
const onPrintPreviewReady = token => { printPreviewToken.value = token }
const printRecords = ref([])
const {
  references: printReferences, checking: checkingPrint, result: printCheck,
  error: printCheckError, checkedTemplateId, begin: beginPrintCheck,
  invalidate: invalidatePrintCheck, check: checkPrintTemplate
} = useCertificatePrintPreflight(validatePrint)
const printReady = computed(() => Boolean(printCheck.value?.canGenerate &&
  checkedTemplateId.value === printTplId.value && !printCheckError.value && !checkingPrint.value))
const printIssueCount = computed(() => printCheck.value?.issueCount || 0)
const checkPrint = () => checkPrintTemplate(printTplId.value)
const closePrint = () => {
  if (printing.value || saving.value) return
  showPrint.value = false
  invalidatePrintCheck()
  printPreviewToken.value = ''
}
watch(printTplId, () => {
  printAttemptError.value = ''
  if (showPrint.value) checkPrint()
}, { flush: 'sync' })

const openPrint = async () => {
  if (openingPrint.value || printing.value) return
  if (!selectedList.value.length) { warning('请先勾选要打印的证书'); return }
  // 打开即固定身份；补录、筛选及当前批次变化均不改变本次范围。
  printRecords.value = selectedList.value.map(c => ({ ...c }))
  beginPrintCheck(printRecords.value)
  printWarnings.value = []
  printAttemptError.value = ''
  printPreviewToken.value = ''
  openingPrint.value = true
  try {
    await Promise.all([dataService.load(), userStore.loadPermissions()])
    printTemplates.value = (dataService.getData('printTemplates') || [])
      .filter(t => (t.docType || 'certificate') === 'certificate')
    if (!printTemplates.value.length) {
      warning('还没有证书打印模板，请先到「模板管理」创建')
      router.push('/templates')
      return
    }
    printTplId.value = printTemplates.value[0]?.id || ''
    showPrint.value = true
    await checkPrint()
  } catch (err) {
    toastError('读取打印模板失败：' + (err.message || err))
  } finally {
    openingPrint.value = false
  }
}

const issueSignature = result => JSON.stringify({
  count: result?.issueCount || 0, truncated: Boolean(result?.truncated),
  issues: result?.issues || []
})

const runPrint = async () => {
  if (printing.value || saving.value || checkingPrint.value || !printReady.value) return
  const tpl = printTemplates.value.find(t => t.id === printTplId.value)
  if (!tpl) { warning('请选择打印模板'); return }
  const acknowledgedIssues = issueSignature(printCheck.value)
  const viewedToken = printPreviewToken.value
  const references = printReferences.value.map(reference => ({ ...reference }))
  printing.value = true
  printWarnings.value = []
  printAttemptError.value = ''
  try {
    const checked = await checkPrintTemplate(tpl.id)
    if (!checked || !checked.canGenerate) return
    if (viewedToken && checked.validationToken !== viewedToken) {
      warning('证书或模板已更新，请查看新的预览后再打印')
      return
    }
    if (checked.issueCount && issueSignature(checked) !== acknowledgedIssues) {
      warning('检查结果已更新，请确认列出的问题后再生成')
      return
    }
    const res = await generatePrint({
      templateId: tpl.id,
      certNumbers: references,
      validationToken: checked.validationToken
    })
    if (!res.success) throw new Error(res.message || '生成失败')
    printWarnings.value = res.warnings || []
    openHtmlWindow(res.html)
    // 生成即归档 + 留痕（失败不阻断打印）
    try {
      await archivePrint({
        html: res.html,
        templateId: tpl.id,
        docType: tpl.docType || 'certificate',
        title: tpl.name,
        itemCount: res.itemCount,
        refIds: references
      })
    } catch (e) { console.warn('打印留痕失败（不阻断）:', e) }
    success(`已生成 ${res.itemCount} 份证书，请在打印窗口确认后打印`)
    loadPrintIndex() // 打印历史即时更新
    showPrint.value = false
    selectedKeys.value = new Set()
  } catch (err) {
    printAttemptError.value = err.message || '生成失败'
    toastError('批量打印失败：' + (err.message || err))
    if (err.status === 409) await checkPrintTemplate(tpl.id)
  } finally {
    printing.value = false
  }
}

const removeCert = async (c) => {
  const ok = await confirm({
    title: '删除证书',
    message: `确定删除证书「${c.certNumber}」（选手：${c.playerName || '—'}）吗？该操作仅影响当前批次下的这一条。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'danger'
  })
  if (!ok) return
  try {
    await certStore.deleteCert(c.certNumber, c.sessionId)
    success('已删除')
  } catch (err) {
    toastError('删除失败：' + (err.message || err))
  }
}

// ===== 批量操作（删除 / 修改字段）=====
// 复用与批量打印同一套勾选（selectedKeys）。勾选只在当前批次内有效，
// 所以这两个操作的作用范围也是「当前批次里勾中的那些」。

/** 可批量修改的字段（与证书表单口径一致） */
const BULK_EDITABLE_FIELDS = [
  { key: 'award', label: '奖项' },
  { key: 'certRound', label: '赛段' },
  { key: 'groupName', label: '组别' },
  { key: 'language', label: '语种' },
  { key: 'instructor', label: '指导老师' },
  { key: 'orgName', label: '选送机构' },
  { key: 'receivingOrg', label: '收件机构' },
  { key: 'promotion', label: '晋级情况' },
  { key: 'workName', label: '作品名称' },
]

const showBulkEdit = ref(false)
const bulkEditField = ref('award')
const bulkEditValue = ref('')
const bulkEditBusy = ref(false)

const bulkEditFieldLabel = computed(() =>
  (BULK_EDITABLE_FIELDS.find(f => f.key === bulkEditField.value) || {}).label || '')

const openBulkEdit = () => {
  if (!selectedList.value.length) return
  bulkEditField.value = BULK_EDITABLE_FIELDS[0].key
  bulkEditValue.value = ''
  showBulkEdit.value = true
}

const applyBulkEdit = async () => {
  const list = selectedList.value
  if (!list.length || bulkEditBusy.value) return
  const patch = { [bulkEditField.value]: bulkEditValue.value }
  bulkEditBusy.value = true
  try {
    const n = await certStore.patchCerts(
      list.map(c => ({ certNumber: c.certNumber, sessionId: c.sessionId || '' })), patch)
    success(`已把 ${n} 份证书的「${bulkEditFieldLabel.value}」改为「${bulkEditValue.value || '（空）'}」`)
    showBulkEdit.value = false
  } catch (err) {
    toastError('批量修改失败：' + (err.message || err))
  } finally {
    bulkEditBusy.value = false
  }
}

const bulkDelete = async () => {
  const list = selectedList.value
  if (!list.length) return
  const ok = await confirm({
    title: '批量删除证书',
    message: `确定删除选中的 ${list.length} 份证书吗？此操作不可撤销，建议先到「设置 → 备份管理」创建一份备份。`,
    confirmText: `删除 ${list.length} 份`,
    cancelText: '取消',
    type: 'danger'
  })
  if (!ok) return
  try {
    const n = await certStore.deleteCerts(
      list.map(c => ({ certNumber: c.certNumber, sessionId: c.sessionId || '' })))
    selectedKeys.value = new Set()
    success(`已删除 ${n} 份证书`)
  } catch (err) {
    toastError('批量删除失败：' + (err.message || err))
  }
}

// 切换证书批次（仅改变可视范围）
const switchSession = async (id) => {
  if (quickDraft.value) return
  try {
    await certStore.switchSession(id)
  } catch (err) {
    toastError('切换批次失败：' + (err.message || err))
  }
}

// 删除证书批次：仅抹除该批次下的证书
const removeSession = async (s) => {
  if (quickDraft.value) return
  const isLegacy = s.id === 'legacy-import'
  const ok = await confirm({
    title: isLegacy ? '删除历史导入批次' : '删除证书批次',
    message: isLegacy
      ? `「历史导入」包含 ${s.count} 条证书，删除后将彻底抹除且不可恢复。确定继续吗？`
      : `确定删除批次「${s.name}」吗？将抹除该批次下的 ${s.count} 条证书，其它批次不受影响。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'danger'
  })
  if (!ok) return
  try {
    const removed = await certStore.deleteSession(s.id)
    success(`已删除批次，抹除 ${removed} 条证书`)
  } catch (err) {
    toastError('删除批次失败：' + (err.message || err))
  }
}

// 保存编号规则（模板 + 默认省/前缀/年）
const saveRules = async () => {
  savingRules.value = true
  try {
    await certStore.updateTemplateSettings({
      templates: { province: tplProvince.value, national: tplNational.value },
      defaults: { province: defProvince.value, code: defCode.value, year: defYear.value }
    })
    success('编号规则已保存')
    showRules.value = false
  } catch (err) {
    toastError('保存规则失败：' + (err.message || err))
  } finally {
    savingRules.value = false
  }
}

const syncRulesFromStore = () => {
  tplProvince.value = certStore.templates.province
  tplNational.value = certStore.templates.national
  defProvince.value = certStore.defaults.province
  defCode.value = certStore.defaults.code
  defYear.value = certStore.defaults.year
}

// 填写抽屉
const editing = ref(null)
const editDrawer = ref(null)
const editFromPrint = ref(false)
const editableCertFields = new Set(['playerName', 'certRound', 'groupName', 'award', 'workName', 'instructor', 'language', 'promotion', 'orgName', 'receivingOrg', 'packed'])
const canFillPrintIssue = issue => Boolean(issue.reference && editableCertFields.has(issue.column))
const openEdit = (c) => {
  if (saving.value || printing.value) return
  if (!canEditCertificates.value) { warning('当前账户没有修改证书的权限'); return }
  editFromPrint.value = false
  editing.value = { ...c }
}
const fillPrintIssue = async issue => {
  if (saving.value || printing.value || checkingPrint.value || !canFillPrintIssue(issue)) return
  if (!canEditCertificates.value) { warning('当前账户没有修改证书的权限'); return }
  const reference = issue.reference
  const record = certificates.value.find(c => String(c.certNumber) === String(reference.certNumber) &&
    (c.sessionId || 'legacy-import') === (reference.sessionId || 'legacy-import'))
  if (!record) { toastError('这份证书已不存在，请重新检查'); await checkPrint(); return }
  editFromPrint.value = true
  editing.value = { ...record }
  showPrint.value = false
  invalidatePrintCheck()
  await nextTick()
  const control = editDrawer.value?.querySelector(`[data-cert-field="${issue.column}"]`)
  const target = control?.matches('input,textarea') ? control : control?.querySelector('.custom-select-trigger')
  if (target) {
    if (!target.matches('input,textarea')) target.setAttribute('tabindex', '-1')
    target.focus()
    target.scrollIntoView?.({ block: 'nearest' })
  }
}
const closeEdit = async () => {
  if (saving.value) return
  editing.value = null
  if (editFromPrint.value) {
    editFromPrint.value = false
    showPrint.value = true
    await checkPrint()
  }
}
const saveEdit = async () => {
  if (!editing.value || saving.value || !canEditCertificates.value) return
  saving.value = true
  let returnToPrint = false
  try {
    const patch = { ...editing.value }
    delete patch.certNumber
    patch.missingWorkName = patch.workName ? 0 : 1
    patch.isWithdrawn = (patch.award || '').includes('退赛') ? 1 : 0
    patch.receivingOrg = patch.receivingOrg || patch.orgName
    const saved = await certStore.updateCert(editing.value.certNumber, patch, editing.value.sessionId)
    if (saved === null) throw new Error('证书已不存在，未保存修改')
    printRecords.value = printRecords.value.map(c => certKey(c) === certKey(editing.value) ? { ...editing.value } : c)
    success('已保存')
    editing.value = null
    returnToPrint = editFromPrint.value
    editFromPrint.value = false
  } catch (err) {
    toastError('保存失败：' + (err.message || err))
  } finally {
    saving.value = false
  }
  if (returnToPrint) {
    showPrint.value = true
    await checkPrint()
  }
}

const renderCharts = () => {
  if (!stats.value.total) return
  const awardData = stats.value.byAward
  if (awardChart.value) {
    if (chartInstances.award) chartInstances.award.destroy()
    chartInstances.award = new Chart(awardChart.value, {
      type: 'bar',
      data: { labels: awardData.map(d => d.award), datasets: [{ label: '证书数', data: awardData.map(d => d.count), backgroundColor: '#b0392b' }] },
      options: { responsive: true, plugins: { legend: { display: false } } }
    })
  }
  const orgData = stats.value.byOrg
  if (orgChart.value) {
    if (chartInstances.org) chartInstances.org.destroy()
    chartInstances.org = new Chart(orgChart.value, {
      type: 'bar',
      data: { labels: orgData.map(d => d.org), datasets: [{ label: '证书数', data: orgData.map(d => d.count), backgroundColor: '#6b5d4f' }] },
      options: { indexAxis: 'y', responsive: true, plugins: { legend: { display: false } } }
    })
  }
}

watch([stats, filtered], () => { nextTick(renderCharts) }, { deep: true })

// ===== 字段完整度概览 + 打印历史（数据透明，不拦截） =====
// 字段清单来自打印字段目录（台账真实数据派生）；空值在维护页即可见，
// 不用到打印弹窗才发现——符合「出口把关 + 过程透明」的分层。
const fieldCatalog = ref([])
const printLogIndex = ref({})

const loadFieldCatalog = async () => {
  try {
    const res = await fetchFieldCatalog()
    if (res.success) fieldCatalog.value = res.fields || []
  } catch { /* 完整度概览失败不阻断页面 */ }
}

const incompleteFields = computed(() => {
  const total = certificates.value.length
  if (!total) return []
  return fieldCatalog.value
    .map(f => {
      const missing = certificates.value.filter(c => {
        const v = c[f.column] ?? c[f.dbColumn]
        return v === null || v === undefined || String(v).trim() === ''
      }).length
      return { ...f, total, missing }
    })
    .filter(f => f.missing > 0)
})

const loadPrintIndex = async () => {
  try {
    const res = await fetchPrintLogs('certificate')
    printLogIndex.value = indexPrintReferences((res.success && res.logs) || [])
  } catch { /* 打印历史失败不阻断页面 */ }
}

const printHist = (c) => printLogIndex.value[printReferenceKey({ certNumber: c.certNumber, sessionId: c.sessionId || '' })]
const legacyPrintHist = (c) => printLogIndex.value[printReferenceKey(c.certNumber)]

onMounted(async () => {
  await Promise.all([
    certStore.loadCertificates(),
    userStore.loadPermissions(),
    projectStore.loadProjects?.(),
    orgStore.loadOrganizations?.(),
    playerStore.loadPlayers?.()
  ].filter(Boolean))
  if (!certStore.loaded || !projectStore.loaded || !orgStore.loaded || !playerStore.loaded) {
    toastError('证书数据加载失败，请刷新后重试')
    return
  }
  syncRulesFromStore()
  applyRouteQuery()
  await Promise.all([loadFieldCatalog(), loadPrintIndex()])
  await nextTick()
  renderCharts()
})

onActivated(async () => {
  await certStore.loadCertificates()
  await Promise.all([
    userStore.loadPermissions(),
    projectStore.loadProjects?.(),
    orgStore.loadOrganizations?.(),
    playerStore.loadPlayers?.()
  ].filter(Boolean))
  if (!certStore.loaded || !projectStore.loaded || !orgStore.loaded || !playerStore.loaded) {
    toastError('证书数据加载失败，请刷新后重试')
    return
  }
  syncRulesFromStore()
  applyRouteQuery()
  await Promise.all([loadFieldCatalog(), loadPrintIndex()])
  await nextTick()
  renderCharts()
})

// 地址栏 query 变化（例如从另一个机构再点进来）时重新应用上下文
watch(() => route.query, () => applyRouteQuery())
</script>

<style scoped>
.certificates-page { padding: 24px; }

/* 拖拽导入遮罩：把 Excel 拖到页面任意处即可导入台账 */
.page-drop-mask {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(59, 130, 246, 0.08);
  border: 3px dashed var(--accent, #3b82f6);
  font-size: 15px;
  font-weight: 500;
  color: var(--accent, #3b82f6);
  pointer-events: none;
}
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; gap: 12px; flex-wrap: wrap; }
.page-header h2 { margin: 0; font-size: 20px; color: var(--text-primary); }
.header-actions { display: flex; gap: 10px; flex-wrap: wrap; }

.panel { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 20px; }
.panel-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.panel-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.7; margin-bottom: 12px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.field { font-size: 13px; color: var(--text-secondary); display: flex; align-items: center; gap: 8px; }

.preview-stats { display: flex; gap: 24px; margin: 12px 0; }
.stat { display: flex; flex-direction: column; }
.stat .num { font-size: 22px; font-weight: 700; color: var(--cinnabar, #b0392b); }
.stat .lbl { font-size: 12px; color: var(--text-secondary); }
.preview-dist { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 12px; }
.dist-title { font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.pill { display: inline-block; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 12px; padding: 2px 10px; font-size: 12px; margin: 0 6px 6px 0; }
.warn-text { font-size: 12px; color: var(--text-secondary); }

.stat-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.stat-card { background: var(--bg-secondary); border-radius: 12px; padding: 16px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.stat-card .num { display: block; font-size: 26px; font-weight: 700; color: var(--text-primary); }
.stat-card .lbl { font-size: 13px; color: var(--text-secondary); }

.filter-bar { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }
.ctx-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding: 8px 14px; background: #f7ece9; border-left: 3px solid var(--cinnabar, #b0392b); border-radius: 6px; }
.ctx-label { font-size: 13px; font-weight: 600; color: var(--cinnabar, #b0392b); }

.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
.chart-card { background: var(--bg-secondary); border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.chart-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-primary); }
.chart-card canvas { max-height: 280px; }

.cert-table-wrap { background: var(--bg-secondary); border-radius: 12px; padding: 8px 16px 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow-x: auto; }
.cert-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.cert-table th, .cert-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }
.cert-table th { color: var(--text-secondary); font-weight: 600; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
.cell-warn { color: var(--cinnabar, #b0392b); }
.badge { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.a-gold { background: #f3e2dd; color: #b0392b; }
.a-silver { background: #eee; color: #555; }
.a-bronze { background: #f0e6da; color: #8a6d3b; }
.a-copper { background: #e8eef0; color: #4a6b78; }
.a-other { background: var(--bg-primary); color: var(--text-secondary); }
.table-foot { margin-top: 12px; }
.ledger-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; font-size: 13px; color: var(--text-primary); }
.quick-cell { min-width: 140px; max-width: 260px; }
.quick-value { display: flex; align-items: center; gap: 8px; text-align: left; font: inherit; color: inherit; border: 1px solid transparent; background: transparent; cursor: text; padding: 5px; border-radius: 5px; overflow-wrap: anywhere; }
.quick-value span { opacity: .35; }
.quick-value:hover, .quick-value:focus-visible { border-color: var(--border); background: var(--bg-primary); }
.quick-value:disabled { cursor: default; }
.quick-editor { display: flex; flex-direction: column; gap: 5px; min-width: 160px; }
.quick-input { width: 100%; min-width: 0; }
.quick-controls { display: flex; gap: 12px; }
.quick-error { font-size: 12px; line-height: 1.5; color: var(--danger, #b0392b); }
.muted { color: var(--text-secondary); font-size: 13px; }

.drawer-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 1000; }
.drawer { position: absolute; top: 0; right: 0; width: 420px; max-width: 92vw; height: 100%; background: var(--bg-primary); display: flex; flex-direction: column; box-shadow: -4px 0 16px rgba(0,0,0,0.18); }
.drawer-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.drawer-body { padding: 16px 20px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 14px; }
.drawer-row { display: flex; flex-direction: column; gap: 6px; }
.drawer-label { font-size: 12px; color: var(--text-secondary); }
.drawer-foot { padding: 14px 20px; border-top: 1px solid var(--border); }

.btn-primary { background: var(--cinnabar, #b0392b); color: #fff; border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-secondary { background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border); border-radius: 8px; padding: 8px 16px; cursor: pointer; }
.btn-secondary.active,
.btn-secondary.active:hover { background: var(--cinnabar, #b0392b); color: #fff; border-color: var(--cinnabar, #b0392b); }
.btn-sm { padding: 6px 12px; font-size: 13px; }
.btn-text { background: none; border: none; color: var(--cinnabar, #b0392b); cursor: pointer; font-size: 13px; }
.btn-text.danger { color: #c0392b; }
.empty-state { padding: 60px 20px; text-align: center; color: var(--text-secondary); }

/* 证书批次条 */
.session-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.session-label { font-size: 13px; color: var(--text-secondary); white-space: nowrap; }
.session-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.session-chip { display: inline-flex; align-items: center; gap: 8px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 18px; background: var(--bg-secondary); color: var(--text-primary); cursor: pointer; font-size: 13px; }
.session-chip.active { border-color: var(--cinnabar, #b0392b); background: #f7ece9; color: var(--cinnabar, #b0392b); font-weight: 600; }
.session-name { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-count { background: rgba(0,0,0,0.06); border-radius: 10px; padding: 0 6px; font-size: 12px; }
.session-chip.active .session-count { background: rgba(176,57,43,0.12); }
.session-del { color: var(--text-secondary); font-size: 16px; line-height: 1; padding: 0 2px; }
.session-del:hover { color: #c0392b; }

/* 行操作：填写与删除拉开间距，避免误点 */
.row-actions { display: inline-flex; align-items: center; gap: 14px; }
.row-sep { width: 1px; height: 14px; background: var(--border); }
/* 字段完整度概览条 */
.completeness-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; background: var(--bg-secondary); border: 1px dashed var(--border); border-radius: 10px; padding: 8px 14px; margin-bottom: 14px; font-size: 13px; color: var(--text-secondary); }
.completeness-bar .bar-label { color: var(--text-primary); font-weight: 600; }
.completeness-bar .comp-item { background: var(--bg-primary); border: 1px solid var(--border); border-radius: 12px; padding: 2px 10px; }
.completeness-bar .bar-hint { opacity: 0.8; }
/* 行内打印历史 */
.print-hist { color: var(--text-secondary); font-size: 12px; cursor: default; }

/* 勾选列与批量打印弹窗 */
.sel-col { width: 36px; text-align: center; }
.print-modal { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 1180px; max-width: 96vw; height: 88vh; background: var(--bg-primary); border-radius: 12px; display: flex; flex-direction: column; box-shadow: 0 8px 32px rgba(0,0,0,0.25); overflow: hidden; }

/* ---------- 批量修改弹窗 ---------- */
.bulk-mask { position: fixed; inset: 0; z-index: 70; background: rgba(0, 0, 0, 0.35); display: flex; align-items: center; justify-content: center; }
.bulk-dialog { width: 460px; max-width: 92vw; background: var(--bg-primary); border-radius: 12px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25); overflow: hidden; }
.bulk-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border); }
.bulk-head strong { font-size: 15px; color: var(--text-primary); }
.bulk-x { border: 0; background: transparent; font-size: 20px; line-height: 1; color: var(--text-secondary); cursor: pointer; padding: 0 4px; }
.bulk-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 14px; }
.bulk-row { display: flex; align-items: center; gap: 12px; }
.bulk-input { flex: 1; min-width: 0; border: 1px solid var(--border); border-radius: 7px; background: var(--bg-primary); color: var(--text-primary); padding: 8px 10px; font-size: 13px; }
.bulk-input:focus { outline: none; border-color: var(--accent); }
.bulk-hint { margin: 0; font-size: 12px; color: var(--text-tertiary); }
.bulk-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 18px; border-top: 1px solid var(--border); }
.print-workspace { display: grid; grid-template-columns: 350px minmax(0, 1fr); flex: 1; min-height: 0; }
.print-settings { border-right: 1px solid var(--border); min-height: 0; padding: 16px; }
.print-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
@media (max-width: 850px) {
  .print-workspace { grid-template-columns: minmax(0, 1fr); overflow-y: auto; }
  .print-settings { overflow: visible; border-right: 0; }
  .print-footer { flex-wrap: wrap; }
  .print-workspace :deep(.certificate-preview) { min-height: 480px; }
}
.print-sel-list { display: flex; flex-wrap: wrap; gap: 6px; }
.print-sel-list .pill { display: inline-block; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 2px 8px; font-size: 12px; }
.print-warn { background: #fff8e1; border: 1px solid #ffe082; border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 4px; }
.print-warn .side-title { font-size: 13px; font-weight: 600; color: #8a6d00; }
.print-preflight { border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.print-preflight-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.print-preflight p { margin: 8px 0; line-height: 1.6; }
.print-issue { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-top: 1px solid var(--border); }
.print-issue-detail { display: flex; flex-direction: column; gap: 5px; flex: 1; min-width: 0; overflow-wrap: anywhere; font-size: 13px; }
.print-issue button { flex-shrink: 0; }
.print-check-error, .print-issue-error { color: var(--danger, #b0392b); }
.print-check-ok { color: var(--success, #26734d); }

/* 编号规则面板 */
.rules-grid { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-end; margin: 12px 0; }
.rules-grid .field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--text-secondary); }
.rules-grid .col { flex: 1 1 260px; }
.rules-grid .mono { font-family: ui-monospace, monospace; }
.rules-preview { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.rules-preview .pill { background: var(--bg-primary); border: 1px solid var(--border); border-radius: 12px; padding: 2px 10px; font-size: 12px; }
.rules-preview .mono { font-family: ui-monospace, monospace; }
</style>
