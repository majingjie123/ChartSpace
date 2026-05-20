/**
 * Excel 多空间智能图表分析工具 - Vue 3 前端应用
 * 使用 Options API 组织复杂组件逻辑
 */
const { createApp, ref, reactive, computed, watch, onMounted, nextTick } = Vue;

const app = createApp({
  data() {
    return {
      // ---- 空间 ----
      spaces: [],
      currentSpaceId: null,

      // ---- 数据集 ----
      datasets: [],

      // ---- 上传流程 ----
      showUploadModal: false,
      uploadStep: 1,
      uploadFile: null,
      uploadDatasetId: null,
      uploadSheets: [],
      uploadSelectedSheet: '',
      uploadPreviewData: { columns: [], rows: [], col_types: {}, total_rows: 0 },
      uploadPreprocess: {
        missing: '',
        sampling: null,
        samplingMethod: 'random',
        samplingN: 50000,
        xType: '',
        xCol: ''
      },
      uploadConfirming: false,

      // ---- 图表 ----
      charts: [],
      renderedCharts: {},
      trendInfos: {},
      showNewChartModal: false,
      showEditChartModal: false,
      editChartId: null,
      newChartStep: 1,
      newChartForm: {
        dataset_id: '', name: '', chart_type: 'scatter',
        x_col: '', y_col: '', y2_col: '',
        trend_enabled: true,
        config: { title: '', x_label: '', y_label: '', color: '#4f6ef7' }
      },
      chartDatasetColumns: [],
      chartLoading: {},

      // ---- AI 配置 ----
      aiConfigs: [],
      showAIConfigModal: false,
      // editAIConfig handled by editingAIConfigId
      aiConfigForm: {
        name: '', base_url: '', api_key: '', model: 'gpt-3.5-turbo',
        system_prompt: '你是一个数据分析助手，基于用户上传的 Excel 数据回答问题。',
        max_tokens: 2000, temperature: 0.7, is_default: false
      },
      editingAIConfigId: null,

      // ---- 聊天 ----
      chatMessages: [],
      chatInput: '',
      chatLoading: false,
      selectedAiDatasetId: null,
      activeTab: 'chat',

      // ---- 笔记 ----
      notes: [],

      // ---- 备份 ----
      showBackupModal: false,

      // ---- 空间重命名 ----
      renamingSpace: false,
      renameSpaceName: '',

      // ---- 通知 ----
      toasts: [],

      // ---- 加载状态 ----
      loading: { spaces: false, datasets: false, charts: false, chat: false, notes: false }
    };
  },

  computed: {
    currentSpace() {
      return this.spaces.find(s => s.id === this.currentSpaceId) || null;
    },
    spaceAiConfigId() {
      return this.currentSpace?.ai_config_id || null;
    }
  },

  watch: {
    currentSpaceId() {
      if (this.currentSpaceId) {
        this.loadDatasets();
        this.loadCharts();
        this.loadChatHistory();
        this.loadNotes();
      } else {
        this.datasets = [];
        this.charts = [];
        this.renderedCharts = {};
        this.trendInfos = {};
        this.chatMessages = [];
        this.notes = [];
      }
    }
  },

  methods: {
    // ======================== 通知 ========================
    toast(msg, type = 'success') {
      const id = Date.now();
      this.toasts.push({ id, msg, type });
      setTimeout(() => {
        this.toasts = this.toasts.filter(t => t.id !== id);
      }, 3000);
    },

    // ======================== API 通用 ========================
    async api(method, url, data = null, isFormData = false) {
      try {
        const cfg = { method, url: '/api' + url };
        if (isFormData) {
          cfg.data = data;
          cfg.headers = { 'Content-Type': 'multipart/form-data' };
        } else if (data !== null) {
          cfg.data = data;
          cfg.headers = { 'Content-Type': 'application/json' };
        }
        const resp = await axios(cfg);
        return resp.data;
      } catch (err) {
        const msg = err.response?.data?.error || err.message || '请求失败';
        this.toast(msg, 'error');
        throw err;
      }
    },

    // ======================== 空间管理 ========================
    async loadSpaces() {
      this.loading.spaces = true;
      try {
        this.spaces = await this.api('GET', '/spaces');
        if (this.spaces.length > 0 && !this.currentSpaceId) {
          this.currentSpaceId = this.spaces[0].id;
        } else if (this.spaces.length === 0) {
          this.currentSpaceId = null;
        }
      } finally {
        this.loading.spaces = false;
      }
    },

    async createSpace() {
      const name = '新空间 ' + (this.spaces.length + 1);
      const space = await this.api('POST', '/spaces', { name });
      this.spaces.unshift(space);
      this.currentSpaceId = space.id;
      this.toast('空间已创建');
    },

    startRenameSpace() {
      if (!this.currentSpace) return;
      this.renamingSpace = true;
      this.renameSpaceName = this.currentSpace.name;
    },

    async confirmRenameSpace() {
      if (!this.renameSpaceName.trim()) return;
      const space = await this.api('PUT', `/spaces/${this.currentSpaceId}`, { name: this.renameSpaceName.trim() });
      const idx = this.spaces.findIndex(s => s.id === space.id);
      if (idx >= 0) this.spaces[idx] = space;
      this.renamingSpace = false;
      this.toast('空间已重命名');
    },

    cancelRenameSpace() {
      this.renamingSpace = false;
    },

    async deleteSpace(id) {
      if (!confirm('确定删除此空间？所有数据将被永久清除。')) return;
      await this.api('DELETE', `/spaces/${id}`);
      this.spaces = this.spaces.filter(s => s.id !== id);
      if (this.currentSpaceId === id) {
        this.currentSpaceId = this.spaces.length > 0 ? this.spaces[0].id : null;
      }
      this.toast('空间已删除');
    },

    switchSpace(id) {
      if (id !== this.currentSpaceId) {
        this.currentSpaceId = id;
      }
    },

    // ======================== 数据集管理 ========================
    async loadDatasets() {
      if (!this.currentSpaceId) return;
      this.loading.datasets = true;
      try {
        this.datasets = await this.api('GET', `/spaces/${this.currentSpaceId}/datasets`);
      } finally {
        this.loading.datasets = false;
      }
    },

    // ---- 上传流程 ----
    resetUploadModal() {
      this.uploadStep = 1;
      this.uploadFile = null;
      this.uploadDatasetId = null;
      this.uploadSheets = [];
      this.uploadSelectedSheet = '';
      this.uploadPreviewData = { columns: [], rows: [], col_types: {}, total_rows: 0 };
      this.uploadPreprocess = {
        missing: '', sampling: null, samplingMethod: 'random',
        samplingN: 50000, xType: '', xCol: ''
      };
      this.uploadConfirming = false;
    },

    openUploadModal() {
      this.resetUploadModal();
      this.showUploadModal = true;
    },

    onUploadFileChange(event) {
      const file = event.target.files[0];
      if (!file) return;
      const ext = file.name.split('.').pop().toLowerCase();
      if (!['xlsx', 'xls'].includes(ext)) {
        this.toast('仅支持 .xlsx 或 .xls 文件', 'error');
        return;
      }
      if (file.size > 50 * 1024 * 1024) {
        this.toast('文件超过 50MB 限制', 'error');
        return;
      }
      this.uploadFile = file;
      this.uploadStep = 2;
    },

    async confirmUploadSheet() {
      if (!this.uploadSelectedSheet && this.uploadSheets.length > 0) {
        this.uploadSelectedSheet = this.uploadSheets[0];
      }
      this.uploadStep = 3;
      await this.loadUploadPreview();
    },

    async loadUploadPreview() {
      try {
        const dsId = this.uploadDatasetId;
        const resp = await this.api('GET', `/datasets/${dsId}/preview?rows=100`);
        this.uploadPreviewData = resp;
        this.uploadPreprocess.xCol = '';
        this.uploadStep = 3;
      } catch (e) { /* error handled by api() */ }
    },

    async uploadFileStep() {
      if (!this.uploadFile) return;
      const formData = new FormData();
      formData.append('file', this.uploadFile);
      const result = await this.api('POST', `/spaces/${this.currentSpaceId}/datasets`, formData, true);
      this.uploadDatasetId = result.dataset_id;
      this.uploadSheets = result.sheets;
      this.uploadSelectedSheet = result.sheets[0] || '';
      this.uploadStep = 2;
    },

    async confirmUploadPreprocess() {
      this.uploadConfirming = true;
      try {
        // Step 1: confirm sheet
        await this.api('POST', `/datasets/${this.uploadDatasetId}/confirm-sheet`, {
          sheet: this.uploadSelectedSheet
        });
        // Step 2: apply preprocessing
        const preprocessOpts = {};
        if (this.uploadPreprocess.missing) {
          preprocessOpts.missing = this.uploadPreprocess.missing;
        }
        if (this.uploadPreprocess.sampling) {
          preprocessOpts.sampling = {
            method: this.uploadPreprocess.samplingMethod,
            n: this.uploadPreprocess.samplingN
          };
        }
        if (this.uploadPreprocess.xType && this.uploadPreprocess.xCol) {
          preprocessOpts.x_type = this.uploadPreprocess.xType;
          preprocessOpts.x_col = this.uploadPreprocess.xCol;
        }
        await this.api('POST', `/datasets/${this.uploadDatasetId}/preprocess`, preprocessOpts);
        this.showUploadModal = false;
        this.toast('数据集上传成功');
        await this.loadDatasets();
      } catch (e) {
        // error handled by api()
      } finally {
        this.uploadConfirming = false;
      }
    },

    async deleteDataset(id) {
      if (!confirm('确定删除此数据集？关联图表也会被删除。')) return;
      await this.api('DELETE', `/datasets/${id}`);
      this.datasets = this.datasets.filter(d => d.id !== id);
      this.charts = this.charts.filter(c => c.dataset_id !== id);
      delete this.renderedCharts[id];
      this.toast('数据集已删除');
    },

    // ======================== 图表管理 ========================
    async loadCharts() {
      if (!this.currentSpaceId) return;
      this.loading.charts = true;
      try {
        this.charts = await this.api('GET', `/spaces/${this.currentSpaceId}/charts`);
        // 逐个渲染
        for (const chart of this.charts) {
          this.renderChart(chart.id);
        }
      } finally {
        this.loading.charts = false;
      }
    },

    async renderChart(chartId) {
      this.chartLoading = { ...this.chartLoading, [chartId]: true };
      try {
        const result = await this.api('GET', `/charts/${chartId}/render`);
        this.renderedCharts = { ...this.renderedCharts, [chartId]: result.chart_html };
        this.trendInfos = { ...this.trendInfos, [chartId]: result.trend_info };
        // 重新执行 Plotly 脚本
        await nextTick();
        const scripts = document.querySelectorAll(`#chart-${chartId} script`);
        scripts.forEach(s => {
          const newScript = document.createElement('script');
          newScript.text = s.textContent;
          s.parentNode.replaceChild(newScript, s);
        });
      } catch (e) {
        this.renderedCharts = { ...this.renderedCharts, [chartId]: '<div class="text-danger p-3">图表渲染失败</div>' };
      } finally {
        this.chartLoading = { ...this.chartLoading, [chartId]: false };
      }
    },

    // ---- 新建图表 ----
    openNewChartModal() {
      this.newChartStep = 1;
      this.newChartForm = {
        dataset_id: this.datasets.length > 0 ? this.datasets[0].id : '',
        name: '', chart_type: 'scatter',
        x_col: '', y_col: '', y2_col: '',
        trend_enabled: true,
        config: { title: '', x_label: '', y_label: '', color: '#4f6ef7' }
      };
      this.chartDatasetColumns = [];
      this.showNewChartModal = true;
      if (this.datasets.length > 0 && this.newChartForm.dataset_id) {
        this.loadChartDatasetColumns(this.newChartForm.dataset_id);
      }
    },

    async loadChartDatasetColumns(datasetId) {
      if (!datasetId) { this.chartDatasetColumns = []; return; }
      try {
        const preview = await this.api('GET', `/datasets/${datasetId}/preview?rows=1`);
        this.chartDatasetColumns = preview.columns.map(c => ({
          name: c,
          type: preview.col_types[c] || 'text'
        }));
      } catch (e) {
        this.chartDatasetColumns = [];
      }
    },

    onNewChartDatasetChange() {
      this.newChartForm.x_col = '';
      this.newChartForm.y_col = '';
      this.newChartForm.y2_col = '';
      this.loadChartDatasetColumns(this.newChartForm.dataset_id);
    },

    async confirmCreateChart() {
      const form = this.newChartForm;
      if (!form.dataset_id || !form.name || !form.x_col || !form.y_col) {
        this.toast('请填完所有必填项', 'warning');
        return;
      }
      try {
        await this.api('POST', `/spaces/${this.currentSpaceId}/charts`, form);
        this.showNewChartModal = false;
        this.toast('图表创建成功');
        await this.loadCharts();
      } catch (e) { /* handled */ }
    },

    // ---- 编辑图表 ----
    openEditChartModal(chart) {
      this.editChartId = chart.id;
      this.newChartForm = {
        dataset_id: chart.dataset_id,
        name: chart.name,
        chart_type: chart.chart_type,
        x_col: chart.x_col,
        y_col: chart.y_col,
        y2_col: chart.y2_col || '',
        trend_enabled: chart.trend_enabled,
        config: chart.config ? (typeof chart.config === 'string' ? JSON.parse(chart.config) : chart.config) : {}
      };
      this.showEditChartModal = true;
      this.loadChartDatasetColumns(chart.dataset_id);
    },

    async confirmEditChart() {
      const form = this.newChartForm;
      if (!form.name || !form.x_col || !form.y_col) {
        this.toast('请填完所有必填项', 'warning');
        return;
      }
      try {
        await this.api('PUT', `/charts/${this.editChartId}`, form);
        this.showEditChartModal = false;
        this.toast('图表已更新');
        await this.loadCharts();
      } catch (e) { /* handled */ }
    },

    async deleteChart(id) {
      if (!confirm('确定删除此图表？')) return;
      await this.api('DELETE', `/charts/${id}`);
      this.charts = this.charts.filter(c => c.id !== id);
      delete this.renderedCharts[id];
      delete this.trendInfos[id];
      this.toast('图表已删除');
    },

    exportChartCsv(chart) {
      window.open(`/api/charts/${chart.id}/export-csv`, '_blank');
    },

    async exportChartImage(chart) {
      try {
        await this.api('POST', `/charts/${chart.id}/export-image`);
        // The API returns a file, we need to download it
        window.open(`/api/charts/${chart.id}/export-image`, '_blank');
        this.toast('图片已导出');
      } catch (e) { /* handled */ }
    },

    // ======================== AI 配置 ========================
    async loadAIConfigs() {
      try {
        this.aiConfigs = await this.api('GET', '/ai-configs');
      } catch (e) { /* handled */ }
    },

    openAIConfigModal() {
      this.editingAIConfigId = null;
      this.resetAIConfigForm();
      this.loadAIConfigs();
      this.showAIConfigModal = true;
    },

    resetAIConfigForm() {
      this.aiConfigForm = {
        name: '', base_url: '', api_key: '', model: 'gpt-3.5-turbo',
        system_prompt: '你是一个数据分析助手，基于用户上传的 Excel 数据回答问题。',
        max_tokens: 2000, temperature: 0.7, is_default: false
      };
      this.editingAIConfigId = null;
    },

    editAIConfig(config) {
      this.editingAIConfigId = config.id;
      this.aiConfigForm = {
        name: config.name,
        base_url: config.base_url,
        api_key: config.api_key,
        model: config.model,
        system_prompt: config.system_prompt || '',
        max_tokens: config.max_tokens,
        temperature: config.temperature,
        is_default: config.is_default
      };
    },

    async saveAIConfig() {
      const f = this.aiConfigForm;
      if (!f.name || !f.base_url || !f.api_key || !f.model) {
        this.toast('请填完所有必填项', 'warning');
        return;
      }
      try {
        if (this.editingAIConfigId && this.editingAIConfigId > 0) {
          await this.api('PUT', `/ai-configs/${this.editingAIConfigId}`, f);
          this.toast('AI 配置已更新');
        } else {
          await this.api('POST', '/ai-configs', f);
          this.toast('AI 配置已创建');
        }
        this.resetAIConfigForm();
        await this.loadAIConfigs();
      } catch (e) { /* handled */ }
    },

    async deleteAIConfig(id) {
      if (!confirm('确定删除此 AI 配置？')) return;
      await this.api('DELETE', `/ai-configs/${id}`);
      await this.loadAIConfigs();
      this.toast('AI 配置已删除');
    },

    async setDefaultAIConfig(id) {
      await this.api('POST', `/ai-configs/${id}/set-default`);
      await this.loadAIConfigs();
      this.toast('默认配置已更新');
    },

    cancelAIConfigEdit() {
      this.resetAIConfigForm();
    },

    // ======================== AI 绑定 & 聊天 ========================
    async bindSpaceAIConfig(aiConfigId) {
      if (!this.currentSpaceId) return;
      try {
        await this.api('POST', `/spaces/${this.currentSpaceId}/ai-config`, { ai_config_id: aiConfigId });
        this.toast('AI 配置已绑定到空间');
      } catch (e) { /* handled */ }
    },

    async sendChatMessage() {
      const msg = this.chatInput.trim();
      if (!msg || this.chatLoading) return;
      this.chatInput = '';
      this.chatLoading = true;
      try {
        const result = await this.api('POST', '/chat', {
          space_id: this.currentSpaceId,
          message: msg,
          dataset_id: this.selectedAiDatasetId || null
        });
        await this.loadChatHistory();
      } catch (e) {
        this.chatLoading = false;
      } finally {
        this.chatLoading = false;
      }
    },

    handleChatKeydown(e) {
      if (e.ctrlKey && e.key === 'Enter') {
        this.sendChatMessage();
      }
    },

    async loadChatHistory() {
      if (!this.currentSpaceId) return;
      this.loading.chat = true;
      try {
        this.chatMessages = await this.api('GET', `/spaces/${this.currentSpaceId}/chat-history`);
      } finally {
        this.loading.chat = false;
      }
    },

    async clearChatHistory() {
      if (!confirm('确定清空所有聊天记录？')) return;
      await this.api('DELETE', `/spaces/${this.currentSpaceId}/chat-history`);
      this.chatMessages = [];
      this.toast('聊天记录已清空');
    },

    // ======================== 分析笔记 ========================
    async loadNotes() {
      if (!this.currentSpaceId) return;
      this.loading.notes = true;
      try {
        this.notes = await this.api('GET', `/spaces/${this.currentSpaceId}/notes`);
      } finally {
        this.loading.notes = false;
      }
    },

    async saveNoteFromChat(msg) {
      if (!msg) return;
      try {
        await this.api('POST', '/notes', {
          space_id: this.currentSpaceId,
          title: msg.content.substring(0, 30) + (msg.content.length > 30 ? '...' : ''),
          content: msg.content
        });
        await this.loadNotes();
        this.toast('已保存为笔记');
      } catch (e) { /* handled */ }
    },

    async deleteNote(id) {
      if (!confirm('确定删除此笔记？')) return;
      await this.api('DELETE', `/notes/${id}`);
      await this.loadNotes();
      this.toast('笔记已删除');
    },

    viewNote(note) {
      // 显示笔记详情
      alert(`【${note.title}】\n\n${note.content}`);
    },

    // ======================== 备份与导出 ========================
    openBackupModal() {
      this.showBackupModal = true;
    },

    downloadBackup() {
      window.open('/api/system/backup', '_blank');
      this.toast('备份下载中');
    },

    async restoreBackup(event) {
      const file = event.target.files[0];
      if (!file) return;
      if (!file.name.endsWith('.db')) {
        this.toast('请选择 .db 备份文件', 'error');
        return;
      }
      if (!confirm('恢复将覆盖当前所有数据，确定继续？')) return;
      const formData = new FormData();
      formData.append('file', file);
      try {
        await this.api('POST', '/system/restore', formData, true);
        this.toast('数据库已恢复，请刷新页面');
        setTimeout(() => location.reload(), 1500);
      } catch (e) { /* handled */ }
    },

    exportSpace() {
      if (!this.currentSpaceId) return;
      window.open(`/api/spaces/${this.currentSpaceId}/export`, '_blank');
      this.toast('空间导出中');
    },

    // ======================== 格式化 ========================
    formatDate(dateStr) {
      if (!dateStr) return '';
      const d = new Date(dateStr);
      return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    },

    formatDateFull(dateStr) {
      if (!dateStr) return '';
      const d = new Date(dateStr);
      return d.toLocaleString('zh-CN');
    },

    numCols(datasetId) {
      const ds = this.datasets.find(d => d.id === datasetId);
      return ds ? (ds.row_count || '?') : '?';
    },

    trendValueClass(direction) {
      if (direction === '上升') return 'up';
      if (direction === '下降') return 'down';
      return 'stable';
    },

    trendIcon(direction) {
      if (direction === '上升') return '↑';
      if (direction === '下降') return '↓';
      return '→';
    },

    chartTypeLabel(type) {
      const labels = { scatter: '散点图', line: '折线图', bar: '柱状图', box: '箱线图', area: '面积图', pie: '饼图' };
      return labels[type] || type;
    },

    renderMarkdown(text) {
      if (!text) return '';
      return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>').replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>');
    },

    exportTrendCsv(chartId) {
      window.open('/api/charts/' + chartId + '/export-csv', '_blank');
    }
  },

  mounted() {
    this.loadSpaces();
    this.loadAIConfigs();
  }
});

app.mount('#app');
