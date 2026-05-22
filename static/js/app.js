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
      editingDatasetId: null,
      editingDatasetName: '',

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
      chartJsons: {},
      trendInfos: {},
      showNewChartModal: false,
      showEditChartModal: false,
      editChartId: null,
      showChartZoomModal: false,
      zoomedChart: null,
      zoomedChartHtml: '',
      newChartStep: 1,
      newChartForm: {
        dataset_id: '', name: '', chart_type: 'scatter',
        x_col: '', y_col: '', y2_col: '',
        trend_enabled: true,
        config: { title: '', x_label: '', y_label: '', color: '#4f6ef7', color2: '#ff7f0e' }
        },      chartDatasetColumns: [],
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
      isChatCollapsed: false,

      // ---- 笔记 ----
      notes: [],
      showNoteDetailModal: false,
      selectedNote: null,

      // ---- 备份 ----
      showBackupModal: false,
      // ---- 退出程序 ----
      showExitConfirm: false,
      // ---- 大文件上传警告 ----
      uploadWarnLarge: null,
      // ---- AI 模型刷新 ----
      refreshingModels: false,
      cachedModelList: [],
      showModelsDropdown: false,

      // ---- 空间重命名 ----
      renamingSpace: false,
      renameSpaceName: '',

      // ---- 通知 ----
      toasts: [],

      // ---- 加载状态 ----
      loading: { spaces: false, datasets: false, charts: false, chat: false, notes: false },

      // ---- 认证 ----
      authRequired: false,
      authenticated: false,
      loginPassword: '',

      // ---- 内存监控 ----
      sysMem: null,
      memTimer: null,
      
      // ---- 数据量级消息 ----
      uploadVolMsg: ''
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

    async loadMemory() {
      try {
        this.sysMem = await this.api('GET', '/system/memory');
      } catch (e) {}
    },

    async checkAuthStatus() {
      try {
        const res = await this.api('GET', '/auth/status');
        this.authRequired = res.required;
        this.authenticated = res.authenticated;
        if (this.authRequired && !this.authenticated) {
          // 停止其他加载直到认证
          return;
        }
        this.initApp();
      } catch (e) {}
    },

    async login() {
      try {
        await this.api('POST', '/auth/login', { password: this.loginPassword });
        this.authenticated = true;
        this.toast('登录成功');
        this.initApp();
      } catch (e) {}
    },

    initApp() {
      this.loadSpaces();
      this.loadAIConfigs();
      this.loadMemory();
      if (this.memTimer) clearInterval(this.memTimer);
      this.memTimer = setInterval(() => this.loadMemory(), 10000);
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
      this.uploadWarnLarge = null;
    },

    openUploadModal() {
      this.resetUploadModal();
      this.showUploadModal = true;
    },

    async onUploadFileChange(event) {
      const file = event.target.files[0];
      if (!file) return;
      // 检查文件大小
      const sizeMB = file.size / (1024 * 1024);
      if (sizeMB > 50) {
        this.toast('文件超过 50MB 限制', 'error');
        return;
      }
      this.uploadFile = file;
      this.uploadStep = 1;
      // 创建 FormData 上传
      const formData = new FormData();
      formData.append('file', file);
      try {
        const result = await this.api('POST', `/spaces/${this.currentSpaceId}/datasets`, formData, true);
        this.uploadDatasetId = result.dataset_id;
        this.uploadSheets = result.sheets || [];
        this.uploadSelectedSheet = result.sheets?.[0] || '';
        this.uploadVolMsg = result.vol_msg || '';
        if (result.vol_level === 'million') {
          alert('⚠️ 百万行级超大文件提醒：\n' + result.vol_msg);
          this.uploadPreprocess.sampling = 'random';
        } else if (result.vol_level === 'hundred_thousand') {
          this.toast(result.vol_msg, 'warning');
        }
        this.uploadStep = 2;
      } catch (e) {
        // error handled by api()
      }
    },

    async confirmUploadSheet() {
      if (!this.uploadSelectedSheet && this.uploadSheets.length > 0) {
        this.uploadSelectedSheet = this.uploadSheets[0];
      }
      try {
        const result = await this.api('POST', `/datasets/${this.uploadDatasetId}/confirm-sheet`, {
          sheet: this.uploadSelectedSheet
        });
        this.uploadVolMsg = result.vol_msg || '';
        if (result.vol_level === 'million') {
          alert('⚠️ 百万行级超大文件提醒：\n' + result.vol_msg);
          this.uploadPreprocess.sampling = 'random';
        }
        this.uploadStep = 3;
        await this.loadUploadPreview();
      } catch (e) { /* handled */ }
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

    startRenameDataset(ds) {
      this.editingDatasetId = ds.id;
      this.editingDatasetName = ds.name;
      this.$nextTick(() => {
        const inputs = this.$refs.dsRenameInput;
        if (inputs && inputs.length > 0) inputs[0].focus();
      });
    },

    async confirmRenameDataset(ds) {
      if (this.editingDatasetId !== ds.id) return;
      const newName = this.editingDatasetName.trim();
      if (!newName || newName === ds.name) {
        this.editingDatasetId = null;
        return;
      }
      try {
        const updated = await this.api('PUT', `/datasets/${ds.id}`, { name: newName });
        const idx = this.datasets.findIndex(d => d.id === ds.id);
        if (idx >= 0) this.datasets[idx].name = updated.name;
        this.toast('数据集已重命名');
      } catch (e) { /* handled */ } finally {
        this.editingDatasetId = null;
      }
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
        // 缓存 JSON 数据供全屏使用
        this.chartJsons = { ...this.chartJsons, [chartId]: result.chart_json };
        this.trendInfos = { ...this.trendInfos, [chartId]: result.trend_info };
        
        await nextTick();
        const container = document.getElementById(`chart-container-${chartId}`);
        if (container && typeof Plotly !== 'undefined') {
          // 清空容器并使用原生方法渲染
          container.innerHTML = '';
          const config = { responsive: true, displayModeBar: false };
          Plotly.newPlot(container, result.chart_json.data, result.chart_json.layout, config);
        }
      } catch (e) {
        const container = document.getElementById(`chart-container-${chartId}`);
        if (container) container.innerHTML = '<div class="text-danger p-3">图表渲染失败，请检查数据集。</div>';
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
        
        // 智能自动填入默认列
        if (this.chartDatasetColumns.length >= 2 && !this.newChartForm.x_col) {
          this.newChartForm.x_col = this.chartDatasetColumns[0].name;
          this.newChartForm.y_col = this.chartDatasetColumns[1].name;
          
          // 自动起名
          const ds = this.datasets.find(d => d.id === datasetId);
          if (ds && !this.newChartForm.name) {
            this.newChartForm.name = `${this.newChartForm.y_col} 随 ${this.newChartForm.x_col} 的分析图`;
            this.newChartForm.config.title = this.newChartForm.name;
          }
        }
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

    zoomChart(chart) {
      this.zoomedChart = chart;
      this.showChartZoomModal = true;

      this.$nextTick(() => {
        setTimeout(() => {
          const container = document.getElementById(`chart-zoom-container-${chart.id}`);
          const jsonData = this.chartJsons[chart.id];
          
          if (container && jsonData && typeof Plotly !== 'undefined') {
            container.innerHTML = '';
            // 深度克隆 layout 以免修改原始缓存，并开启响应式
            const fullLayout = JSON.parse(JSON.stringify(jsonData.layout));
            fullLayout.autosize = true;
            
            const config = { responsive: true, displayModeBar: false };
            Plotly.newPlot(container, jsonData.data, fullLayout, config);
            
            // 强制触发一次 resize
            Plotly.Plots.resize(container);
          }
        }, 300);
      });
    },

    exportChartCsv(chart) {
      window.open(`/api/charts/${chart.id}/export-csv`, '_blank');
    },

    exportChartImage(chart) {
      const el = document.getElementById(`chart-${chart.id}`);
      if (el && typeof Plotly !== 'undefined') {
        this.toast('正在生成图片...');
        Plotly.downloadImage(el, {
          format: 'png',
          width: 1200,
          height: 700,
          filename: `${chart.name}_数据分析图`
        }).then(() => {
          this.toast('导出成功');
        }).catch(err => {
          console.error('前端导出失败，尝试后端导出', err);
          window.open(`/api/charts/${chart.id}/export-image`, '_blank');
        });
      } else {
        window.open(`/api/charts/${chart.id}/export-image`, '_blank');
        this.toast('后端导出中，请稍候...');
      }
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
      this.cachedModelList = [];
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
      this.cachedModelList = config.cached_models || [];
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

    async refreshAIModels() {
      this.refreshingModels = true;
      try {
        let result;
        const f = this.aiConfigForm;
        if (Number.isInteger(this.editingAIConfigId)) {
          // 已有保存的配置 → 用已有记录刷新
          result = await this.api('POST', `/ai-configs/${this.editingAIConfigId}/refresh-models`);
        } else {
          // 新建模式 → 用表单值预览刷新
          if (!f.base_url || !f.api_key) {
            this.toast('请先填写 base_url 和 api_key', 'warning');
            return;
          }
          result = await this.api('POST', '/ai-configs/refresh-models-preview', {
            base_url: f.base_url,
            api_key: f.api_key
          });
        }
        this.cachedModelList = result.models || [];
        this.toast(result.message || '模型列表已刷新');
        if (this.cachedModelList.length > 0) {
          this.aiConfigForm.model = this.cachedModelList[0];
        }
      } catch (e) {
        // handled by api()
      } finally {
        this.refreshingModels = false;
      }
    },

    // ======================== AI 绑定 & 聊天 ========================
    async bindSpaceAIConfig(aiConfigId) {
      if (!this.currentSpaceId) return;
      const id = (aiConfigId === 'null' || !aiConfigId) ? null : parseInt(aiConfigId);
      try {
        await this.api('POST', `/spaces/${this.currentSpaceId}/ai-config`, { ai_config_id: id });
        const idx = this.spaces.findIndex(s => s.id === this.currentSpaceId);
        if (idx >= 0) {
          this.spaces[idx].ai_config_id = id;
        }
        this.toast(id ? 'AI 配置已绑定到空间' : '已恢复为默认 AI 配置');
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
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendChatMessage();
      }
    },

    async copyToClipboard(text) {
      if (!text) return;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
          this.toast('已复制到剪贴板');
        } else {
          // 回退到 execCommand
          const textArea = document.createElement("textarea");
          textArea.value = text;
          document.body.appendChild(textArea);
          textArea.select();
          document.execCommand("copy");
          document.body.removeChild(textArea);
          this.toast('已复制到剪贴板');
        }
      } catch (err) {
        this.toast('复制失败', 'error');
      }
    },

    async loadChatHistory() {
      if (!this.currentSpaceId) return;
      this.loading.chat = true;
      try {
        this.chatMessages = await this.api('GET', `/spaces/${this.currentSpaceId}/chat-history`);
        await this.$nextTick();
        this.scrollChatToBottom();
      } finally {
        this.loading.chat = false;
      }
    },

    scrollChatToBottom() {
      const container = this.$refs.chatMessagesRef;
      if (container) {
        container.scrollTop = container.scrollHeight;
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
      this.selectedNote = note;
      this.showNoteDetailModal = true;
    },

    // ======================== 备份与导出 ========================
    openBackupModal() {
      this.showBackupModal = true;
    },

    async exitApp() {
      try {
        await this.api('POST', '/system/shutdown');
        this.showExitConfirm = false;
        this.toast('程序正在关闭...');
        setTimeout(() => {
          document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;"><div style="text-align:center;"><h2>👋 程序已退出</h2><p style="color:#666;">您可以关闭此窗口</p></div></div>';
        }, 1000);
      } catch (e) {
        // handled by api()
      }
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
      // 使用 marked.js 渲染 Markdown
      if (typeof marked !== 'undefined') {
        return marked.parse(text);
      }
      // 回退方案：基本的转义和换行处理
      return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
    },

    exportTrendCsv(chartId) {
      window.open('/api/charts/' + chartId + '/export-csv', '_blank');
    }
  },

  mounted() {
    this.checkAuthStatus();
  }
});

app.mount('#app');
