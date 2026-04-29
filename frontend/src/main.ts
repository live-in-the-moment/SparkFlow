import './styles.css';

type SectionId = 'dashboard' | 'projects' | 'workbench' | 'report' | 'knowledge' | 'cost' | 'settings';
type LogLevel = 't' | 'ok' | 'warn' | 'err';
type AgentState = 'running' | 'done' | 'warn';
type IssueType = 'major' | 'normal' | 'suggest';

type Agent = {
  id: string;
  name: string;
  emoji: string;
  desc: string;
};

type LiveIssue = {
  type: IssueType;
  title: string;
  tag: string;
  body: string;
};

type KnowledgeResult = {
  code: string;
  title: string;
  tag: string;
  body: string;
  scope: string;
  voltage: string;
  citations: string;
  score: number;
};

declare global {
  interface Window {
    showToast: (text: string) => void;
    goWorkbenchAndRun: () => void;
    startReview: () => void;
    resetReview: () => void;
    manualIntervention: () => void;
    searchKb: () => void;
    presetKb: (text: string) => void;
  }
}

const sections: Record<SectionId, readonly [string, string]> = {
  dashboard: [
    '仪表板',
    '实时监控评审项目状态与多智能体运行效能',
  ],
  projects: ['项目中心', '统一管理工程项目、设计文件、解析结果和评审状态；从文件上传开始建立证据链。'],
  workbench: [
    '智能评审台',
    '7个专业/职能智能体并行工作，主审Agent进行汇总、冲突仲裁、风险定级和人工复核流转。',
  ],
  report: ['评审报告', '输出可追溯、可复核、可闭环的结构化评审意见，而不是单纯的自然语言总结。'],
  knowledge: ['规范知识库', 'RAG增强检索，向量语义搜索 + 关键词过滤，条文溯源'],
  cost: ['造价分析', '工程量联动校验，历史造价对比，孤立森林异常检测'],
  settings: ['配置中心', '系统参数、模型配置、Agent行为规则管理'],
};

const agents: Agent[] = [
  { id: 'primary', name: '电气一次Agent', emoji: '⚡', desc: '主接线、设备选型、短路电流、间隔配置一致性' },
  { id: 'secondary', name: '电气二次Agent', emoji: '🧩', desc: '继电保护、自动化、二次回路、通信接口' },
  { id: 'civil', name: '土建Agent', emoji: '🏗️', desc: '结构荷载、基础布置、抗震设防、坐标一致性' },
  { id: 'line', name: '线路Agent', emoji: '🗼', desc: '路径、杆塔、导线力学、交叉跨越' },
  { id: 'code', name: '规范合规Agent', emoji: '📚', desc: '强制性条文、行业规范、企业标准、历史意见' },
  { id: 'cost', name: '造价分析Agent', emoji: '💰', desc: '工程量清单、历史指标、单价和数量异常' },
  { id: 'safety', name: '安全评估Agent', emoji: '🛡️', desc: '安全距离、接地、消防通道、运维风险' },
  { id: 'chief', name: '主审Agent', emoji: '🧠', desc: '意见汇总、冲突仲裁、评分定级、报告生成' },
];

const logs: Array<readonly [LogLevel, string]> = [
  ['t', 'LangGraph: 创建项目状态图，载入项目元数据与文件清单。'],
  ['ok', '文件解析完成：识别 DWG 12份、PDF 8份、设计说明书 1份、工程量清单 1份。'],
  ['t', '并行启动：电气一次、电气二次、土建、线路、规范、造价、安全Agent。'],
  ['warn', '规范合规Agent: 发现设计说明中规范版本字段缺失，已标记为可追溯性问题。'],
  ['warn', '电气一次Agent: 设备表与一次接线图主变容量描述不一致，触发跨文件一致性校验。'],
  ['warn', '土建Agent: GIS室设备基础坐标与电气布置图存在偏差，建议专业复核。'],
  ['warn', '造价分析Agent: 电缆工程量较历史同类项目偏离超过阈值，需补充路径依据。'],
  ['ok', '安全评估Agent: 消防通道与接地说明完成初筛，未发现阻断性问题。'],
  ['t', '主审Agent: 对各Agent意见进行去重、合并、风险定级。'],
  ['err', '触发条件边：重大问题需要人工确认，进入专业负责人复核节点。'],
  ['ok', '评审报告草稿已生成：重大2项、一般5项、建议8项。'],
];

const liveIssues: LiveIssue[] = [
  {
    type: 'major',
    title: '主变容量参数跨文件不一致',
    tag: '重大',
    body: '设备参数表与一次接线图中的主变容量描述不一致，可能影响短路电流校核、设备开断能力和保护配置。证据链：设备表第2页；一次图A-01。',
  },
  {
    type: 'normal',
    title: 'GIS室基础坐标与电气布置图偏差',
    tag: '一般',
    body: '土建平面图与电气平面图的设备基础坐标存在偏差，需复核安装净距、检修通道与设备基础尺寸。证据链：T-03/E-05。',
  },
  {
    type: 'normal',
    title: '电缆工程量偏离历史指标',
    tag: '一般',
    body: '部分电缆工程量较同类型项目偏离超过20%，需补充路径计算或备用量设置依据。证据链：工程量清单第18行；历史项目对标。',
  },
  {
    type: 'suggest',
    title: '规范版本未完整列明',
    tag: '建议',
    body: '设计说明引用了部分规范名称，但未列出标准版本和生效日期，影响后续审计追溯。建议补充规范版本清单。',
  },
];

const kbData: KnowledgeResult[] = [
  {
    code: 'NB/T 32004-2018 §5.3.2',
    title: '分布式电源并网逆变器低电压穿越能力要求',
    tag: '强制性条文',
    body: '当电力系统发生故障导致并网点电压跌落时，分布式电源应能在规定的电压跌落范围和时间间隔内不脱网连续运行。当电压跌至20%额定电压时，逆变器应至少维持运行625ms；当电压跌至0时，应至少维持运行150ms。',
    scope: '分布式光伏/风电',
    voltage: '380V~35kV',
    citations: '128次',
    score: 96,
  },
  {
    code: 'GB/T 19964-2012 §8.2',
    title: '光伏发电站防孤岛保护配置要求',
    tag: '推荐性标准',
    body: '光伏发电站应配置防孤岛保护。当电网失压时，应在2s内将光伏发电站与电网断开。容量超过400kW的光伏发电站，应配置主动式防孤岛保护功能。',
    scope: '光伏发电站',
    voltage: '全部',
    citations: '86次',
    score: 89,
  },
  {
    code: 'GB 50797-2012 §6.4.2',
    title: '光伏方阵布置间距与阴影遮挡计算',
    tag: '强制性条文',
    body: '光伏方阵各排、列间布置间距应保证全年09:00~15:00（当地真太阳时）时段内前、后、左、右互不遮挡。间距计算应按冬至日太阳高度角和方位角进行。',
    scope: '光伏发电站',
    voltage: '全部',
    citations: '64次',
    score: 82,
  },
];

let running = false;
let timers: number[] = [];
let selectedProjectName = '珠海110kV景林输变电工程 初设评审';

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);

  if (!element) {
    throw new Error(`Missing required element: #${id}`);
  }

  return element as T;
}

function isSectionId(value: string | undefined): value is SectionId {
  return Boolean(value && value in sections);
}

function createTextElement<K extends keyof HTMLElementTagNameMap>(
  tagName: K,
  text: string,
  className?: string,
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tagName);
  element.textContent = text;

  if (className) {
    element.className = className;
  }

  return element;
}

function renderAgents(): void {
  const grid = requireElement<HTMLDivElement>('agentGrid');
  grid.innerHTML = agents
    .map(
      (agent) => `
      <div class="agent" id="agent-${agent.id}">
        <h4><span>${agent.emoji} ${agent.name}</span><span class="pill blue" id="status-${agent.id}">待启动</span></h4>
        <p>${agent.desc}</p>
        <div class="progress"><div id="progress-${agent.id}"></div></div>
        <small id="small-${agent.id}">等待主审调度</small>
      </div>
    `,
    )
    .join('');
}

function navTo(id: SectionId): void {
  document.querySelectorAll<HTMLElement>('.section').forEach((section) => {
    section.classList.toggle('active', section.id === id);
  });

  document.querySelectorAll<HTMLElement>('.nav-btn').forEach((button) => {
    button.classList.toggle('active', button.dataset.section === id);
  });

  requireElement('pageTitle').textContent = sections[id][0];
  requireElement('pageDesc').textContent = sections[id][1];
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function appendLog(cls: LogLevel, text: string): void {
  const consoleEl = requireElement<HTMLDivElement>('console');
  const line = document.createElement('div');
  const time = createTextElement('span', `[${new Date().toLocaleTimeString()}]`, 't');
  const message = createTextElement('span', text, cls);

  line.append(time, ' ', message);
  consoleEl.appendChild(line);
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

function setAgent(id: string, progress: number, status: string, cls: AgentState = 'running', note = '正在分析'): void {
  const box = requireElement<HTMLDivElement>(`agent-${id}`);
  const bar = requireElement<HTMLDivElement>(`progress-${id}`);
  const statusEl = requireElement<HTMLSpanElement>(`status-${id}`);
  const small = requireElement<HTMLElement>(`small-${id}`);

  box.className = `agent ${cls}`;
  bar.style.width = `${progress}%`;
  statusEl.className = `pill ${cls === 'done' ? 'green' : cls === 'warn' ? 'yellow' : 'blue'}`;
  statusEl.textContent = status;
  small.textContent = note;
}

function createRiskItem(issue: LiveIssue): HTMLDivElement {
  const item = document.createElement('div');
  const head = document.createElement('div');
  const title = createTextElement('h4', issue.title);
  const tag = createTextElement('span', issue.tag, `risk ${issue.type}`);
  const body = createTextElement('p', issue.body);

  item.className = `risk-item ${issue.type}`;
  head.className = 'risk-head';
  head.append(title, tag);
  item.append(head, body);

  return item;
}

function resetReview(): void {
  timers.forEach(window.clearTimeout);
  timers = [];
  running = false;
  renderAgents();
  requireElement('console').innerHTML = '';
  requireElement('issueCounter').textContent = '已发现 0 项';
  requireElement('liveRisks').replaceChildren(
    createRiskItem({
      type: 'suggest',
      title: '等待评审启动',
      tag: '提示',
      body: '启动后，各专业Agent会并行输出问题，并由主审Agent进行合并、去重和风险定级。',
    }),
  );
  showToast('评审演示已重置。');
}

function startReview(): void {
  if (running) {
    showToast('评审演示正在运行。');
    return;
  }

  resetReview();
  running = true;
  showToast(`已启动评审演示：${selectedProjectName}`);

  logs.forEach((item, index) => {
    timers.push(window.setTimeout(() => appendLog(item[0], item[1]), index * 780 + 200));
  });

  agents.forEach((agent, index) => {
    timers.push(window.setTimeout(() => setAgent(agent.id, 28, '分析中', 'running', '正在抽取要素与检索证据'), 300 + index * 110));
    timers.push(window.setTimeout(() => setAgent(agent.id, 66, '校验中', 'running', '执行跨文件/跨专业校验'), 1700 + index * 135));
    timers.push(
      window.setTimeout(() => {
        const hasFinding = ['primary', 'civil', 'cost', 'code'].includes(agent.id);
        setAgent(
          agent.id,
          100,
          hasFinding ? '有发现' : '完成',
          hasFinding ? 'warn' : 'done',
          hasFinding ? '发现需复核问题，已提交主审Agent' : '完成评审，未发现阻断性风险',
        );
      }, 3500 + index * 160),
    );
  });

  timers.push(
    window.setTimeout(() => {
      const list = requireElement<HTMLDivElement>('liveRisks');
      list.replaceChildren();

      liveIssues.forEach((issue, index) => {
        timers.push(
          window.setTimeout(() => {
            list.appendChild(createRiskItem(issue));
            requireElement('issueCounter').textContent = `已发现 ${index + 1} 项`;
          }, index * 520),
        );
      });
    }, 2300),
  );

  timers.push(
    window.setTimeout(() => {
      setAgent('chief', 100, '待人工确认', 'warn', '重大问题已触发人工复核节点');
      requireElement('majorKpi').textContent = '9';
      showToast('评审草稿已生成：重大2项、一般5项、建议8项。');
      running = false;
    }, 7200),
  );
}

function manualIntervention(): void {
  appendLog('err', '人工介入: 专业负责人已接管重大问题，AI意见进入待确认状态。');
  setAgent('chief', 100, '人工介入', 'warn', '等待专业负责人确认');
  showToast('已触发人工介入节点：重大问题不会自动关闭。');
}

function goWorkbenchAndRun(): void {
  navTo('workbench');
  window.setTimeout(startReview, 250);
}

function selectProject(project: HTMLElement): void {
  const projectName = project.dataset.projectName;

  if (!projectName) {
    return;
  }

  selectedProjectName = projectName;

  document.querySelectorAll<HTMLElement>('.project-selectable').forEach((item) => {
    const selected = item === project;
    item.classList.toggle('selected', selected);
    item.setAttribute('aria-pressed', String(selected));
  });

  showToast(`已选择项目：${selectedProjectName}`);
}

function startSelectedProjectReview(): void {
  showToast(`准备启动：${selectedProjectName}`);
  goWorkbenchAndRun();
}

function showToast(text: string): void {
  const toast = requireElement<HTMLDivElement>('toast');
  toast.textContent = text;
  toast.classList.add('show');
  window.setTimeout(() => toast.classList.remove('show'), 2800);
}

function createKnowledgeResult(result: KnowledgeResult): HTMLDivElement {
  const item = document.createElement('div');
  const header = document.createElement('div');
  const code = createTextElement('span', result.code, 'knowledge-code');
  const tag = createTextElement('span', result.tag, 'knowledge-tag');
  const title = createTextElement('h3', result.title);
  const body = createTextElement('p', result.body);
  const meta = document.createElement('div');
  const score = createTextElement('div', `语义相似度：${result.score}%`, 'semantic-score');
  const bar = document.createElement('div');
  const fill = document.createElement('span');

  item.className = 'knowledge-result-card';
  header.className = 'knowledge-result-header';
  meta.className = 'knowledge-meta';
  bar.className = 'semantic-bar';
  fill.style.width = `${result.score}%`;

  header.append(code, tag);
  meta.append(
    createTextElement('span', `适用范围：${result.scope}`),
    createTextElement('span', `电压等级：${result.voltage}`),
    createTextElement('span', `被引用：${result.citations}`),
  );
  bar.append(fill);
  item.append(header, title, body, meta, score, bar);

  return item;
}

function renderKb(results: KnowledgeResult[]): void {
  requireElement('kbResults').replaceChildren(...results.map(createKnowledgeResult));
}

function searchKb(): void {
  const query = requireElement<HTMLInputElement>('kbQuery').value.trim();
  showToast(query ? `语义检索：${query}` : '未输入问题，展示默认示例。');
  renderKb(kbData);
}

function presetKb(text: string): void {
  requireElement<HTMLInputElement>('kbQuery').value = text;
  searchKb();
}

function handleKeyboardAction(event: KeyboardEvent, action: () => void): void {
  if (event.key !== 'Enter' && event.key !== ' ') {
    return;
  }

  event.preventDefault();
  action();
}

function initInteractions(): void {
  document.querySelectorAll<HTMLElement>('.nav-btn').forEach((button) => {
    button.addEventListener('click', () => {
      if (isSectionId(button.dataset.section)) {
        navTo(button.dataset.section);
      }
    });
  });

  const uploadZone = document.querySelector<HTMLElement>('.upload-zone');
  uploadZone?.setAttribute('role', 'button');
  uploadZone?.setAttribute('tabindex', '0');
  uploadZone?.addEventListener('keydown', (event) => {
    handleKeyboardAction(event, () => {
      showToast('演示模式：已模拟上传 DWG、PDF、设计说明书和工程量清单。');
    });
  });

  document.querySelectorAll<HTMLElement>('.project-selectable').forEach((project) => {
    project.setAttribute('role', 'button');
    project.setAttribute('tabindex', '0');
    project.setAttribute('aria-pressed', String(project.classList.contains('selected')));
    project.addEventListener('click', () => selectProject(project));
    project.addEventListener('keydown', (event) => {
      handleKeyboardAction(event, () => selectProject(project));
    });
  });

  document.querySelector<HTMLButtonElement>('#startSelectedProject')?.addEventListener('click', startSelectedProjectReview);

  document.querySelectorAll<HTMLButtonElement>('.filter-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      document.querySelectorAll<HTMLButtonElement>('.filter-chip').forEach((item) => {
        item.classList.toggle('active', item === chip);
      });
    });
  });
}

function exposePrototypeActions(): void {
  window.showToast = showToast;
  window.goWorkbenchAndRun = goWorkbenchAndRun;
  window.startReview = startReview;
  window.resetReview = resetReview;
  window.manualIntervention = manualIntervention;
  window.searchKb = searchKb;
  window.presetKb = presetKb;
}

exposePrototypeActions();
initInteractions();
renderAgents();
renderKb(kbData);
appendLog('t', '系统就绪：等待选择项目并启动评审。');
