import './styles.css';

type PageId = 'dashboard' | 'projects' | 'review' | 'reports' | 'knowledge' | 'cost' | 'settings';

type Agent = {
  id: number;
  name: string;
  logs: string[];
};

const pageTitles: Record<PageId, string> = {
  dashboard: '仪表板',
  projects: '项目中心',
  review: '智能评审台',
  reports: '评审报告',
  knowledge: '规范知识库',
  cost: '造价分析',
  settings: '配置中心',
};

const agents: Agent[] = [
  {
    name: '电气一次Agent',
    id: 1,
    logs: [
      '解析主接线图...',
      '提取变压器参数：SZ11-240000/220',
      '校验短路电流：Isc=25.6kA',
      '比对GB 50060-2008第4.1.4条...',
      '⚠️ 发现：开关柜动稳定不满足要求',
    ],
  },
  {
    name: '电气二次Agent',
    id: 2,
    logs: [
      '解析二次接线图...',
      '提取保护配置清单',
      '核查继电保护整定值',
      '比对GB/T 19964-2012第8.2条...',
      '⚠️ 发现：缺少防孤岛保护配置',
    ],
  },
  {
    name: '土建Agent',
    id: 3,
    logs: [
      '解析总平面布置图...',
      '提取光伏组件布置坐标',
      '计算冬至日阴影长度',
      '比对GB 50797-2012第6.4.2条...',
      '⚠️ 发现：组件间距不足，遮挡率18%',
    ],
  },
  {
    name: '线路Agent',
    id: 4,
    logs: [
      '解析电缆路径图...',
      '提取电缆型号YJV22-3×240',
      '校验电缆载流量',
      '比对GB 50217-2018第3.6.1条...',
      '✓ 电缆选型满足要求',
    ],
  },
  {
    name: '规范合规Agent',
    id: 5,
    logs: [
      '加载规范向量库...',
      '检索相关条文127条',
      '过滤强制性条文23条',
      '交叉验证各Agent引用条文...',
      '✓ 规范引用准确性校验通过',
    ],
  },
  {
    name: '造价分析Agent',
    id: 6,
    logs: [
      '提取工程量清单...',
      '加载历史造价指标库（1,247个项目）',
      '运行孤立森林异常检测...',
      '⚠️ 发现：逆变器单价偏离均值+28%',
      '⚠️ 发现：支架单价偏离均值+35%',
    ],
  },
  {
    name: '安全评估Agent',
    id: 7,
    logs: [
      '解析接地设计图...',
      '提取土壤电阻率数据',
      '计算接地电阻理论值',
      '比对GB/T 50065-2011第4.2.1条...',
      '⚠️ 发现：接地电阻不满足要求',
    ],
  },
];

let reviewRunning = false;

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);

  if (!element) {
    throw new Error(`Missing required element: #${id}`);
  }

  return element as T;
}

function showPage(pageId: PageId): void {
  document.querySelectorAll<HTMLElement>('.page').forEach((page) => {
    page.classList.toggle('active', page.id === pageId);
  });

  document.querySelectorAll<HTMLElement>('.nav-item[data-page]').forEach((navItem) => {
    navItem.classList.toggle('active', navItem.dataset.page === pageId);
  });

  requireElement('page-title').textContent = pageTitles[pageId];
}

function addLog(time: string, agent: string, message: string, type = ''): void {
  const consoleEl = requireElement<HTMLDivElement>('console');
  const line = document.createElement('div');
  const timeEl = document.createElement('span');
  const agentEl = document.createElement('span');
  const messageEl = document.createElement('span');

  line.className = 'console-line';
  timeEl.className = 'console-time';
  timeEl.textContent = time;
  agentEl.className = 'console-agent';
  agentEl.textContent = `[${agent}]`;
  messageEl.className = `console-msg ${type}`.trim();
  messageEl.textContent = message;

  line.append(timeEl, agentEl, messageEl);
  consoleEl.appendChild(line);
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

async function startReview(): Promise<void> {
  if (reviewRunning) {
    return;
  }

  reviewRunning = true;
  showPage('review');
  requireElement<HTMLDivElement>('console').innerHTML = '';

  addLog('09:27:00', '系统', '评审任务 PRJ-2026-046 启动，LangGraph状态机初始化...', 'success');
  addLog('09:27:01', '编排器', '创建并行节点：7个专业Agent同时运行');

  await Promise.all(agents.map((agent, index) => runAgent(agent, index)));

  addLog('09:28:45', '编排器', '所有专业Agent已完成，触发汇聚节点 → 主审Agent', 'success');
  await runChiefAgent();

  addLog('09:29:10', '系统', '评审报告已生成，综合评分：82.5/100', 'success');
  reviewRunning = false;
}

function runAgent(agent: Agent, index: number): Promise<void> {
  return new Promise((resolve) => {
    const dot = requireElement<HTMLSpanElement>(`dot-${agent.id}`);
    const status = requireElement<HTMLSpanElement>(`status-${agent.id}`);
    const progress = requireElement<HTMLDivElement>(`prog-${agent.id}`);
    const card = requireElement<HTMLDivElement>(`agent-${agent.id}`);

    dot.className = 'status-dot running';
    status.textContent = '运行中...';
    card.classList.add('active');

    let step = 0;
    const interval = window.setInterval(() => {
      if (step >= agent.logs.length) {
        window.clearInterval(interval);
        dot.className = 'status-dot done';
        status.textContent = '已完成';
        progress.style.width = '100%';
        card.classList.remove('active');
        resolve();
        return;
      }

      const log = agent.logs[step];
      const type = log.includes('⚠️') ? 'warn' : log.includes('✓') ? 'success' : '';
      const time = `09:27:${(10 + index * 3 + step * 2).toString().padStart(2, '0')}`;
      addLog(time, agent.name, log, type);
      progress.style.width = `${((step + 1) / agent.logs.length) * 100}%`;
      step += 1;
    }, 600 + Math.random() * 400);
  });
}

function runChiefAgent(): Promise<void> {
  return new Promise((resolve) => {
    const dot = requireElement<HTMLSpanElement>('dot-8');
    const status = requireElement<HTMLSpanElement>('status-8');
    const progress = requireElement<HTMLDivElement>('prog-8');
    const card = requireElement<HTMLDivElement>('agent-8');

    dot.className = 'status-dot running';
    status.textContent = '冲突仲裁中...';
    card.classList.add('active');

    const logs = [
      '接收7个专业Agent评审意见...',
      '检测到交叉冲突：电气一次Agent与造价Agent对开关柜数量认定不一致（5 vs 6）',
      '冲突消解：以图纸标注为准，确认6面，标记为"需人工复核"',
      '风险定级：严重缺陷2条 / 重大缺陷3条 / 一般缺陷8条',
      '生成结构化评审报告...',
    ];

    let step = 0;
    const interval = window.setInterval(() => {
      if (step >= logs.length) {
        window.clearInterval(interval);
        dot.className = 'status-dot done';
        status.textContent = '报告已生成';
        progress.style.width = '100%';
        card.classList.remove('active');
        resolve();
        return;
      }

      const time = `09:28:${(50 + step * 5).toString().padStart(2, '0')}`;
      addLog(time, '主审Agent', logs[step], step === 1 ? 'warn' : 'success');
      progress.style.width = `${((step + 1) / logs.length) * 100}%`;
      step += 1;
    }, 800);
  });
}

function handleKeyboardAction(event: KeyboardEvent, action: () => void): void {
  if (event.key !== 'Enter' && event.key !== ' ') {
    return;
  }

  event.preventDefault();
  action();
}

function initInteractions(): void {
  document.querySelectorAll<HTMLElement>('[data-page]').forEach((control) => {
    const pageId = control.dataset.page as PageId | undefined;

    if (!pageId) {
      return;
    }

    control.addEventListener('click', () => showPage(pageId));
  });

  const uploadZone = document.querySelector<HTMLElement>('[data-action="mock-upload"]');

  uploadZone?.addEventListener('click', () => {
    window.alert('模拟文件上传：支持CAD(.dwg)、PDF、Excel清单、Word说明');
  });
  uploadZone?.addEventListener('keydown', (event) => {
    handleKeyboardAction(event, () => {
      window.alert('模拟文件上传：支持CAD(.dwg)、PDF、Excel清单、Word说明');
    });
  });

  document.querySelector<HTMLElement>('[data-action="start-review"]')?.addEventListener('click', () => {
    void startReview();
  });
}

initInteractions();
