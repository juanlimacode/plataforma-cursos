/* Frontend modular da Plataforma Gamificada de Cursos */

const state = {
    user: null,
    courses: [],
    activeCourse: null,
    activeProgress: null,
    currentFilter: 'all',
    pendingUnit: null,
    editingUserId: null,
    adminUsers: [],
    adminCourses: [],
    mdPreviewValid: false,
    toastTimer: null,
};

function escapeHtml(str) {
    return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

async function api(url, options = {}) {
    const opts = {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
    };
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && !url.includes('/api/auth/login') && !url.includes('/api/auth/me')) {
        state.user = null;
        showView('login');
        throw new Error(data.error || 'Sessão expirada.');
    }
    if (!res.ok) {
        throw new Error(data.error || `Erro HTTP ${res.status}`);
    }
    return data;
}

// ---------------- TEMA CLARO / ESCURO ----------------

function initTheme() {
    const saved = localStorage.getItem('plataforma_theme') || 'light';
    applyTheme(saved);
}

function toggleTheme() {
    const isDark = document.documentElement.classList.contains('dark');
    const next = isDark ? 'light' : 'dark';
    localStorage.setItem('plataforma_theme', next);
    applyTheme(next);
}

function applyTheme(theme) {
    const html = document.documentElement;
    if (theme === 'dark') {
        html.classList.add('dark');
    } else {
        html.classList.remove('dark');
    }
    const icon = document.getElementById('themeToggleIcon');
    const label = document.getElementById('themeToggleLabel');
    if (icon && label) {
        icon.className = theme === 'dark' ? 'fa-solid fa-sun text-[11px] text-amber-400' : 'fa-solid fa-moon text-[11px]';
        label.innerText = theme === 'dark' ? 'Claro' : 'Escuro';
    }
}

// ---------------- INICIALIZAÇÃO E NAVEGAÇÃO ----------------

document.addEventListener('DOMContentLoaded', async () => {
    initTheme();

    document.addEventListener('click', (e) => {
        const wrapper = document.getElementById('backupMenuWrapper');
        if (wrapper && !wrapper.contains(e.target)) {
            closeBackupMenu();
        }
    });

    try {
        const res = await api('/api/auth/me');
        state.user = res.user;
        onAuthenticated();
    } catch {
        showView('login');
    }
});

function showView(viewName) {
    ['loginView', 'dashboardView', 'courseView', 'adminView'].forEach((id) => {
        document.getElementById(id).classList.add('hidden');
    });

    const header = document.getElementById('appHeader');
    const courseStats = document.getElementById('courseHeaderStats');

    if (viewName === 'login') {
        header.classList.add('hidden');
        document.getElementById('loginView').classList.remove('hidden');
        return;
    }

    header.classList.remove('hidden');
    if (viewName === 'course') {
        courseStats.classList.remove('hidden');
        courseStats.classList.add('flex');
    } else {
        courseStats.classList.add('hidden');
        courseStats.classList.remove('flex');
        document.getElementById('headerTitle').innerText = 'Plataforma de Estudos';
        document.getElementById('headerSubtitle').innerText = 'Trilhas Gamificadas';
    }

    document.getElementById(`${viewName}View`).classList.remove('hidden');
}

function navigateTo(viewName) {
    if (viewName === 'dashboard') {
        loadDashboard();
    } else if (viewName === 'admin') {
        if (state.user?.role !== 'admin') return;
        loadAdminView();
    }
}

function onAuthenticated() {
    document.getElementById('currentUserBadge').innerText = `${state.user.display_name} (${state.user.username})`;
    const adminBtn = document.getElementById('navAdminBtn');
    if (state.user.role === 'admin') {
        adminBtn.classList.remove('hidden');
        adminBtn.classList.add('inline-flex');
    } else {
        adminBtn.classList.add('hidden');
        adminBtn.classList.remove('inline-flex');
    }
    loadDashboard();
}

// ---------------- AUTENTICAÇÃO ----------------

async function handleLogin(event) {
    event.preventDefault();
    const errBox = document.getElementById('loginError');
    errBox.classList.add('hidden');

    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    const btn = document.getElementById('loginSubmitBtn');
    btn.disabled = true;

    try {
        const res = await api('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
        state.user = res.user;
        document.getElementById('loginPassword').value = '';
        onAuthenticated();
    } catch (err) {
        errBox.innerText = err.message;
        errBox.classList.remove('hidden');
    } finally {
        btn.disabled = false;
    }
}

async function logout() {
    try {
        await api('/api/auth/logout', { method: 'POST' });
    } catch { /* ignore */ }
    state.user = null;
    state.activeCourse = null;
    state.activeProgress = null;
    showView('login');
}

// ---------------- DASHBOARD DE CURSOS ----------------

async function loadDashboard() {
    showView('dashboard');
    try {
        const data = await api('/api/courses');
        state.courses = data.courses || [];
        renderDashboardCourses();
        checkLegacyMigration();
    } catch (err) {
        showToast('Erro', err.message, 'rose');
    }
}

function renderDashboardCourses() {
    const grid = document.getElementById('coursesGrid');
    if (!state.courses.length) {
        grid.innerHTML = `
            <div class="col-span-full bg-surface dark:bg-[#181A1F] border border-line dark:border-zinc-800 rounded-xl p-8 text-center space-y-2">
                <div class="text-sm font-semibold text-ink dark:text-zinc-100">Nenhum curso liberado</div>
                <p class="text-xs text-muted dark:text-zinc-400">Solicite ao administrador a liberação dos cursos para o seu usuário.</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = state.courses.map((c) => {
        const s = c.stats;
        const hasStarted = s.completedUnitsCount > 0;
        const isDone = s.percent === 100 && s.totalUnitsCount > 0;
        return `
            <div class="bg-surface dark:bg-[#181A1F] border ${isDone ? 'border-emerald-600/50 dark:border-emerald-500/40' : 'border-line dark:border-zinc-800'} border-t-4 border-t-amber-400 rounded-xl p-5 flex flex-col justify-between gap-4 hover:border-zinc-400 dark:hover:border-zinc-600 transition-colors">
                <div class="space-y-2.5">
                    <div class="flex items-center justify-between gap-2 text-[11px] font-mono text-muted dark:text-zinc-400">
                        <span class="uppercase tracking-wider text-amber-700 dark:text-amber-400 font-semibold">${escapeHtml(c.category || 'Curso')}</span>
                        <span class="tabular-nums px-2 py-0.5 rounded bg-paper dark:bg-zinc-900 border border-line dark:border-zinc-800">Nível ${s.level}</span>
                    </div>
                    <h3 class="text-base font-bold text-ink dark:text-zinc-100 tracking-tight">${escapeHtml(c.title)}</h3>
                    <p class="text-xs text-muted dark:text-zinc-400 leading-relaxed line-clamp-3">${escapeHtml(c.description)}</p>
                </div>

                <div class="space-y-3 pt-2 border-t border-line dark:border-zinc-800">
                    <div class="space-y-1.5">
                        <div class="flex justify-between text-xs">
                            <span class="text-muted dark:text-zinc-400">Progresso</span>
                            <span class="font-mono font-semibold text-ink dark:text-zinc-100 tabular-nums">${s.percent}%</span>
                        </div>
                        <div class="w-full bg-zinc-200 dark:bg-zinc-800 rounded-full h-2 overflow-hidden">
                            <div class="bg-gradient-to-r from-amber-500 via-amber-400 to-emerald-500 h-full rounded-full transition-all" style="width: ${s.percent}%"></div>
                        </div>
                    </div>

                    <div class="flex items-center justify-between text-[11px] font-mono text-muted dark:text-zinc-400 tabular-nums">
                        <span>${s.completedModulesCount}/${s.totalModulesCount} módulos</span>
                        <span class="text-amber-700 dark:text-amber-400 font-semibold">${s.totalXp} XP</span>
                        <span>${s.unlockedTrophiesCount}/${s.totalTrophiesCount} conquistas</span>
                    </div>

                    <button type="button" onclick="openCourse('${escapeHtml(c.id)}')" class="w-full py-2 rounded-lg bg-zinc-900 dark:bg-amber-500 hover:bg-zinc-800 dark:hover:bg-amber-400 text-white dark:text-zinc-950 text-xs font-semibold transition-colors">
                        ${isDone ? 'Revisar curso' : (hasStarted ? 'Continuar' : 'Iniciar curso')}
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// ---------------- MIGRAÇÃO LEGADA (localStorage) ----------------

function checkLegacyMigration() {
    const banner = document.getElementById('migrationBanner');
    const dismissed = localStorage.getItem('power_bi_migration_dismissed');
    const hasPbiCourse = state.courses.some((c) => c.id === 'power-bi-power-platform');
    if (dismissed || !hasPbiCourse) {
        banner.classList.add('hidden');
        return;
    }
    try {
        const legacy = JSON.parse(localStorage.getItem('power_bi_study_state_v2') || 'null');
        if (legacy && Array.isArray(legacy.completedUnits) && legacy.completedUnits.length > 0) {
            banner.classList.remove('hidden');
            return;
        }
    } catch { /* ignore */ }
    banner.classList.add('hidden');
}

function dismissMigration() {
    localStorage.setItem('power_bi_migration_dismissed', '1');
    document.getElementById('migrationBanner').classList.add('hidden');
}

async function runLocalMigration() {
    try {
        const legacy = JSON.parse(localStorage.getItem('power_bi_study_state_v2') || 'null');
        if (!legacy || !Array.isArray(legacy.completedUnits)) return;
        const res = await api('/api/courses/power-bi-power-platform/migrate-local', {
            method: 'POST',
            body: JSON.stringify({ completedUnits: legacy.completedUnits }),
        });
        localStorage.setItem('power_bi_migration_dismissed', '1');
        document.getElementById('migrationBanner').classList.add('hidden');
        showToast('Progresso migrado', `${res.migratedCount} unidade(s) importada(s) para sua conta.`, 'green');
        loadDashboard();
    } catch (err) {
        showToast('Erro na migração', err.message, 'rose');
    }
}

// ---------------- VISUALIZAÇÃO DO CURSO ----------------

async function openCourse(courseId) {
    try {
        const data = await api(`/api/courses/${encodeURIComponent(courseId)}`);
        state.activeCourse = data.course;
        state.activeProgress = data.progress;
        state.currentFilter = 'all';

        document.getElementById('headerTitle').innerText = data.course.title;
        document.getElementById('headerSubtitle').innerText = data.course.source || data.course.category || 'Curso';
        document.getElementById('courseSourceBadge').innerText = data.course.source ? `Trilha Oficial • ${data.course.source}` : (data.course.category || 'Curso');
        document.getElementById('courseTitle').innerText = data.course.title;
        document.getElementById('courseDescription').innerText = data.course.description || '';

        showView('course');
        renderCourseFilters();
        renderPaths();
        updateCourseDashboard();
    } catch (err) {
        showToast('Erro', err.message, 'rose');
    }
}

function renderCourseFilters() {
    const container = document.getElementById('pathFiltersContainer');
    const paths = state.activeCourse?.paths || [];
    let html = `
        <button type="button" onclick="filterPath('all')" id="filter-all" class="px-3 py-1.5 rounded-lg ${state.currentFilter === 'all' ? 'bg-zinc-900 dark:bg-amber-500 text-white dark:text-zinc-950' : 'bg-surface dark:bg-zinc-900 border border-line dark:border-zinc-700 text-muted dark:text-zinc-300 hover:text-ink dark:hover:text-white'} font-medium transition-colors">
            Todos
        </button>
    `;
    paths.forEach((p) => {
        const shortLabel = p.title.replace(/^Trilha\s*\d+\s*:\s*/i, '');
        const active = state.currentFilter === p.id;
        html += `
            <button type="button" onclick="filterPath('${escapeHtml(p.id)}')" id="filter-${escapeHtml(p.id)}" class="px-3 py-1.5 rounded-lg ${active ? 'bg-zinc-900 dark:bg-amber-500 text-white dark:text-zinc-950' : 'bg-surface dark:bg-zinc-900 border border-line dark:border-zinc-700 text-muted dark:text-zinc-300 hover:text-ink dark:hover:text-white'} font-medium transition-colors">
                ${escapeHtml(shortLabel)}
            </button>
        `;
    });
    container.innerHTML = html;
}

function filterPath(pathId) {
    state.currentFilter = pathId;
    renderCourseFilters();
    renderPaths();
}

const PATH_THEMES = [
    {
        dot: 'bg-amber-400',
        borderLeft: 'border-l-amber-400',
        badge: 'bg-amber-50 dark:bg-amber-500/15 text-amber-800 dark:text-amber-300 border-amber-200 dark:border-amber-500/30',
        bar: 'bg-amber-500',
    },
    {
        dot: 'bg-teal-500',
        borderLeft: 'border-l-teal-500',
        badge: 'bg-teal-50 dark:bg-teal-500/15 text-teal-800 dark:text-teal-300 border-teal-200 dark:border-teal-500/30',
        bar: 'bg-teal-600',
    },
    {
        dot: 'bg-sky-600',
        borderLeft: 'border-l-sky-600',
        badge: 'bg-sky-50 dark:bg-sky-500/15 text-sky-800 dark:text-sky-300 border-sky-200 dark:border-sky-500/30',
        bar: 'bg-sky-600',
    },
];

function renderPaths() {
    const container = document.getElementById('pathsContainer');
    container.innerHTML = '';

    const completedSet = new Set(state.activeProgress?.completedUnits || []);
    const allPaths = state.activeCourse?.paths || [];
    const paths = allPaths.filter((p) => state.currentFilter === 'all' || p.id === state.currentFilter);

    paths.forEach((path) => {
        const pathIdx = Math.max(0, allPaths.findIndex((p) => p.id === path.id));
        const theme = PATH_THEMES[pathIdx % PATH_THEMES.length];

        const pathSection = document.createElement('div');
        pathSection.className = 'space-y-4';

        let pathHtml = `
            <div class="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
                <h4 class="text-base font-bold text-ink dark:text-zinc-100 tracking-tight flex items-center gap-2">
                    <span class="w-2.5 h-2.5 rounded-sm ${theme.dot} shrink-0"></span>
                    <span>${escapeHtml(path.title)}</span>
                </h4>
                <p class="text-xs text-muted dark:text-zinc-400">${escapeHtml(path.description)}</p>
            </div>
            <div class="grid grid-cols-1 gap-4">
        `;

        path.courses.forEach((course, index) => {
            const totalUnits = course.units.length;
            const completedUnitsInCourse = course.units.filter((u) => completedSet.has(u.id)).length;
            const isComplete = completedUnitsInCourse === totalUnits && totalUnits > 0;
            const percent = totalUnits > 0 ? Math.round((completedUnitsInCourse / totalUnits) * 100) : 0;
            const courseNum = String(index + 1).padStart(2, '0');

            pathHtml += `
                <div class="bg-surface dark:bg-[#181A1F] border ${isComplete ? 'border-emerald-600/40 dark:border-emerald-500/40 bg-emerald-50/20 dark:bg-emerald-950/15 border-l-4 border-l-emerald-500' : `border-line dark:border-zinc-800 border-l-4 ${theme.borderLeft}`} rounded-xl p-5 transition-colors">
                    <div class="flex flex-col md:flex-row md:items-start justify-between gap-4 mb-4">
                        <div class="space-y-1.5 flex-grow min-w-0">
                            <div class="flex flex-wrap items-center gap-2 text-xs">
                                <span class="font-mono font-semibold px-1.5 py-0.5 rounded border ${theme.badge} tabular-nums">${courseNum}</span>
                                ${course.tag ? `<span class="text-muted dark:text-zinc-400 font-medium">${escapeHtml(course.tag)}</span>` : ''}
                                ${isComplete ? '<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 text-[11px] font-semibold"><i class="fa-solid fa-check text-[9px]"></i>Concluído</span>' : ''}
                            </div>
                            <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                                <h5 class="text-base font-bold text-ink dark:text-zinc-100 tracking-tight">${escapeHtml(course.title)}</h5>
                                ${course.url ? `<a href="${escapeHtml(course.url)}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-xs font-semibold text-brand dark:text-sky-400 hover:underline whitespace-nowrap"><span>Abrir link</span><i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i></a>` : ''}
                            </div>
                            <p class="text-xs text-muted dark:text-zinc-400 leading-relaxed max-w-3xl">${escapeHtml(course.description)}</p>
                        </div>

                        <div class="flex items-center gap-4 bg-paper dark:bg-zinc-900 px-3.5 py-2 rounded-lg border border-line dark:border-zinc-800 shrink-0 self-start">
                            <div>
                                <div class="text-[10px] uppercase tracking-wider text-muted dark:text-zinc-400 font-medium">XP</div>
                                <div class="text-xs font-mono font-semibold text-amber-700 dark:text-amber-400 tabular-nums">+${course.xp}</div>
                            </div>
                            <div class="h-6 w-px bg-line dark:bg-zinc-800"></div>
                            <div>
                                <div class="text-[10px] uppercase tracking-wider text-muted dark:text-zinc-400 font-medium">Unidades</div>
                                <div class="text-xs font-mono font-semibold text-ink dark:text-zinc-100 tabular-nums">${completedUnitsInCourse}/${totalUnits}</div>
                            </div>
                        </div>
                    </div>

                    <div class="w-full bg-zinc-100 dark:bg-zinc-800 rounded-full h-1.5 mb-4 overflow-hidden">
                        <div class="${isComplete ? 'bg-emerald-600' : theme.bar} h-full transition-all duration-300" style="width: ${percent}%;"></div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
            `;

            course.units.forEach((unit, uIdx) => {
                const isChecked = completedSet.has(unit.id);
                const xpApprox = totalUnits > 0 ? Math.round(course.xp / totalUnits) : 0;
                pathHtml += `
                    <button type="button" onclick="promptToggleUnit('${escapeHtml(unit.id)}', '${escapeHtml(unit.title)}', '${escapeHtml(course.title)}', ${xpApprox}, ${isChecked})" class="text-left cursor-pointer flex items-center justify-between p-2.5 rounded-lg border ${isChecked ? 'bg-emerald-50/70 dark:bg-emerald-950/30 border-emerald-600/30 dark:border-emerald-500/40 text-ink dark:text-zinc-100' : 'bg-paper/60 dark:bg-zinc-900/70 border-line dark:border-zinc-800 hover:bg-paper dark:hover:bg-zinc-800 hover:border-zinc-300 dark:hover:border-zinc-700 text-ink dark:text-zinc-200'} transition-colors">
                        <div class="flex items-center gap-2.5 min-w-0">
                            <span class="w-4 h-4 rounded flex items-center justify-center text-[10px] font-mono shrink-0 transition-colors ${isChecked ? 'bg-emerald-600 text-white' : 'bg-surface dark:bg-zinc-800 text-muted dark:text-zinc-400 border border-zinc-300 dark:border-zinc-700'}">
                                ${isChecked ? '<i class="fa-solid fa-check text-[9px]"></i>' : (uIdx + 1)}
                            </span>
                            <span class="text-xs font-medium truncate ${isChecked ? 'line-through text-muted dark:text-zinc-400' : ''}">${escapeHtml(unit.title)}</span>
                        </div>
                        <span class="text-[11px] font-mono text-muted dark:text-zinc-400 ml-2 whitespace-nowrap tabular-nums">${escapeHtml(unit.time)}</span>
                    </button>
                `;
            });

            pathHtml += '</div></div>';
        });

        pathHtml += '</div>';
        pathSection.innerHTML = pathHtml;
        container.appendChild(pathSection);
    });
}

function updateCourseDashboard() {
    const p = state.activeProgress;
    if (!p) return;

    document.getElementById('userXp').innerText = `${p.totalXp} XP`;
    document.getElementById('userLevel').innerText = p.level;
    document.getElementById('progressBar').style.width = `${p.percent}%`;
    document.getElementById('progressPercentage').innerText = `${p.percent}%`;
    document.getElementById('completedUnitsCount').innerText = `${p.completedUnitsCount} unidades`;
    document.getElementById('completedModulesCount').innerText = `${p.completedModulesCount} de ${p.totalModulesCount} módulos`;

    renderTrophies();
}

function renderTrophies() {
    const container = document.getElementById('trophiesContainer');
    const trophies = state.activeProgress?.trophies || [];
    container.innerHTML = '';

    let unlockedCount = 0;
    trophies.forEach((t) => {
        if (t.unlocked) unlockedCount++;
        const card = document.createElement('div');
        card.className = `p-3.5 rounded-xl border transition-colors flex flex-col gap-2 ${t.unlocked ? 'bg-surface dark:bg-[#181A1F] border-amber-400/70 dark:border-amber-500/50 shadow-sm' : 'bg-surface/60 dark:bg-[#181A1F]/60 border-line dark:border-zinc-800 text-muted dark:text-zinc-400'}`;
        card.innerHTML = `
            <div class="flex items-center justify-between">
                <div class="w-8 h-8 rounded-lg flex items-center justify-center text-sm ${t.unlocked ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300' : 'bg-paper dark:bg-zinc-900 text-zinc-400 dark:text-zinc-500 border border-line dark:border-zinc-800'}">
                    <i class="${escapeHtml(t.icon)}"></i>
                </div>
                <span class="text-[10px] font-mono font-medium px-2 py-0.5 rounded ${t.unlocked ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300' : 'bg-paper dark:bg-zinc-900 text-muted dark:text-zinc-500 border border-line dark:border-zinc-800'}">
                    ${t.unlocked ? 'Liberado' : 'Bloqueado'}
                </span>
            </div>
            <div>
                <div class="text-xs font-bold ${t.unlocked ? 'text-ink dark:text-zinc-100' : 'text-muted dark:text-zinc-400'}">${escapeHtml(t.title)}</div>
                <div class="text-[11px] text-muted dark:text-zinc-400 mt-0.5 leading-snug">${escapeHtml(t.desc)}</div>
            </div>
        `;
        container.appendChild(card);
    });

    document.getElementById('trophyCountText').innerText = `${unlockedCount}/${trophies.length} desbloqueadas`;
}

// ---------------- MODAL DE CONFIRMAÇÃO DE UNIDADE ----------------

function promptToggleUnit(unitId, unitTitle, moduleTitle, xpApprox, currentlyChecked) {
    state.pendingUnit = { unitId, unitTitle, xpApprox, currentlyChecked };
    document.getElementById('confirmUnitTitle').innerText = currentlyChecked ? 'Desmarcar unidade?' : 'Concluir unidade?';
    document.getElementById('confirmUnitDesc').innerText = currentlyChecked
        ? `Ao desmarcar "${unitTitle}" (${moduleTitle}), cerca de ${xpApprox} XP serão removidos e suas conquistas serão recalculadas.`
        : `Confirmar conclusão de "${unitTitle}" (${moduleTitle}) para somar ~${xpApprox} XP ao seu perfil?`;
    document.getElementById('confirmUnitModal').classList.remove('hidden');
}

function closeConfirmUnitModal() {
    state.pendingUnit = null;
    document.getElementById('confirmUnitModal').classList.add('hidden');
}

async function executeToggleUnit() {
    if (!state.pendingUnit || !state.activeCourse) return;
    const { unitId, xpApprox } = state.pendingUnit;
    const prevTrophies = new Set(state.activeProgress?.unlockedTrophies || []);
    closeConfirmUnitModal();

    try {
        const res = await api(`/api/courses/${encodeURIComponent(state.activeCourse.id)}/units/${encodeURIComponent(unitId)}/toggle`, {
            method: 'POST',
        });
        state.activeProgress = res.progress;
        renderPaths();
        updateCourseDashboard();

        const nextTrophies = new Set(res.progress.unlockedTrophies || []);
        const gained = [...nextTrophies].filter((id) => !prevTrophies.has(id));
        const lost = [...prevTrophies].filter((id) => !nextTrophies.has(id));

        if (gained.length > 0) {
            const t = res.progress.trophies.find((item) => item.id === gained[0]);
            showToast('Conquista desbloqueada', t ? t.title : 'Nova conquista!', 'green');
        } else if (lost.length > 0) {
            showToast('Conquista revertida', 'Requisito não atendido após desmarcar.', 'blue');
        } else if (res.completed) {
            showToast('Unidade concluída', `+${xpApprox} XP aproximados.`, 'green');
        } else {
            showToast('Unidade desmarcada', 'XP e progresso recalculados.', 'blue');
        }
    } catch (err) {
        showToast('Erro', err.message, 'rose');
    }
}

// ---------------- BACKUP & RESET DO CURSO ----------------

function toggleBackupMenu(e) {
    e.stopPropagation();
    document.getElementById('backupMenu').classList.toggle('hidden');
}

function closeBackupMenu() {
    const menu = document.getElementById('backupMenu');
    if (menu) menu.classList.add('hidden');
}

function exportJSON() {
    if (!state.activeCourse || !state.activeProgress) return;
    const payload = {
        courseId: state.activeCourse.id,
        completedUnits: state.activeProgress.completedUnits,
        unlockedTrophies: state.activeProgress.unlockedTrophies,
    };
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(payload, null, 2));
    const a = document.createElement('a');
    a.setAttribute('href', dataStr);
    a.setAttribute('download', `progresso_${state.activeCourse.id}_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(a);
    a.click();
    a.remove();
    showToast('Backup exportado', 'Arquivo JSON gerado.', 'blue');
}

function importJSON(event) {
    const file = event.target.files[0];
    if (!file || !state.activeCourse) return;

    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const parsed = JSON.parse(e.target.result);
            if (!parsed || !Array.isArray(parsed.completedUnits)) {
                showToast('Erro', 'Arquivo JSON inválido.', 'rose');
                return;
            }
            const res = await api(`/api/courses/${encodeURIComponent(state.activeCourse.id)}/import-json`, {
                method: 'POST',
                body: JSON.stringify({ completedUnits: parsed.completedUnits, replace: true }),
            });
            state.activeProgress = res.progress;
            renderPaths();
            updateCourseDashboard();
            showToast('Progresso restaurado', `${res.importedCount} unidade(s) carregada(s).`, 'green');
        } catch (err) {
            showToast('Erro', err.message || 'Falha ao ler JSON.', 'rose');
        }
    };
    reader.readAsText(file);
    event.target.value = '';
}

async function resetCourseProgress() {
    if (!state.activeCourse) return;
    if (!window.confirm('Deseja realmente reiniciar todo o seu progresso neste curso?')) return;
    try {
        const res = await api(`/api/courses/${encodeURIComponent(state.activeCourse.id)}/reset`, { method: 'POST' });
        state.activeProgress = res.progress;
        renderPaths();
        updateCourseDashboard();
        showToast('Curso reiniciado', 'Todas as unidades foram desmarcadas.', 'blue');
    } catch (err) {
        showToast('Erro', err.message, 'rose');
    }
}

// ---------------- PAINEL ADMINISTRATIVO ----------------

async function loadAdminView() {
    showView('admin');
    switchAdminTab('users');
    await Promise.all([loadAdminUsersAndCourses()]);
}

function switchAdminTab(tab) {
    ['users', 'courses', 'progress'].forEach((t) => {
        document.getElementById(`adminSection-${t}`).classList.toggle('hidden', t !== tab);
        const btn = document.getElementById(`adminTab-${t}`);
        btn.className = t === tab
            ? 'px-3 py-1.5 rounded-lg bg-zinc-900 dark:bg-amber-500 text-white dark:text-zinc-950 font-medium'
            : 'px-3 py-1.5 rounded-lg bg-surface dark:bg-zinc-900 border border-line dark:border-zinc-700 text-muted dark:text-zinc-300 hover:text-ink dark:hover:text-white font-medium';
    });
    if (tab === 'progress') {
        loadAdminProgress();
    }
}

async function loadAdminUsersAndCourses() {
    try {
        const [usersRes, coursesRes] = await Promise.all([
            api('/api/admin/users'),
            api('/api/admin/courses'),
        ]);
        state.adminUsers = usersRes.users || [];
        state.adminCourses = coursesRes.courses || [];
        renderNewUserCoursesCheckboxes();
        renderAdminUsersTable();
        renderAdminCoursesList();
    } catch (err) {
        showToast('Erro', err.message, 'rose');
    }
}

function renderNewUserCoursesCheckboxes() {
    const box = document.getElementById('newUserCoursesChecks');
    box.innerHTML = '<span class="font-medium text-ink">Liberar cursos:</span>' + state.adminCourses.map((c) => `
        <label class="inline-flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" name="newUserCourse" value="${escapeHtml(c.id)}" class="rounded border-line">
            <span>${escapeHtml(c.title)}</span>
        </label>
    `).join('');
}

function renderAdminUsersTable() {
    const tbody = document.getElementById('adminUsersTableBody');
    const courseTitles = Object.fromEntries(state.adminCourses.map((c) => [c.id, c.title]));

    tbody.innerHTML = state.adminUsers.map((u) => {
        const coursesText = u.role === 'admin'
            ? '<span class="text-muted dark:text-zinc-400">Todos (Admin)</span>'
            : (u.course_ids.length ? u.course_ids.map((id) => escapeHtml(courseTitles[id] || id)).join(', ') : '<span class="text-muted dark:text-zinc-400">Nenhum</span>');

        return `
            <tr class="hover:bg-paper/60 dark:hover:bg-zinc-900/50">
                <td class="px-4 py-3">
                    <div class="font-semibold text-ink dark:text-zinc-100">${escapeHtml(u.display_name)}</div>
                    <div class="font-mono text-[11px] text-muted dark:text-zinc-400">@${escapeHtml(u.username)}</div>
                </td>
                <td class="px-4 py-3 font-mono dark:text-zinc-300">${u.role === 'admin' ? 'ADMIN' : 'Usuário'}</td>
                <td class="px-4 py-3">
                    <span class="px-2 py-0.5 rounded text-[11px] font-medium ${u.active ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300' : 'bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-400'}">
                        ${u.active ? 'Ativo' : 'Desativado'}
                    </span>
                </td>
                <td class="px-4 py-3 font-mono tabular-nums dark:text-zinc-300">${u.total_xp} XP • Nv ${u.level}</td>
                <td class="px-4 py-3 max-w-xs truncate dark:text-zinc-300">${coursesText}</td>
                <td class="px-4 py-3 text-right">
                    <button type="button" onclick="openUserEditModal(${u.id})" class="px-2.5 py-1 rounded border border-line dark:border-zinc-700 bg-surface dark:bg-zinc-900 hover:bg-paper dark:hover:bg-zinc-800 text-xs font-medium dark:text-zinc-200">
                        Editar / Acessos
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

async function adminCreateUser(event) {
    event.preventDefault();
    const username = document.getElementById('newUsername').value.trim();
    const display_name = document.getElementById('newDisplayName').value.trim();
    const password = document.getElementById('newPassword').value;
    const role = document.getElementById('newRole').value;
    const course_ids = [...document.querySelectorAll('input[name="newUserCourse"]:checked')].map((el) => el.value);

    try {
        await api('/api/admin/users', {
            method: 'POST',
            body: JSON.stringify({ username, display_name, password, role, course_ids }),
        });
        document.getElementById('createUserForm').reset();
        showToast('Usuário criado', `@${username} adicionado.`, 'green');
        await loadAdminUsersAndCourses();
    } catch (err) {
        showToast('Erro', err.message, 'rose');
    }
}

function openUserEditModal(userId) {
    const user = state.adminUsers.find((u) => u.id === userId);
    if (!user) return;
    state.editingUserId = userId;
    document.getElementById('userEditModalTitle').innerText = `Editar: ${user.username}`;
    document.getElementById('editDisplayName').value = user.display_name;
    document.getElementById('editRole').value = user.role;
    document.getElementById('editActive').value = user.active ? 'true' : 'false';
    document.getElementById('editNewPassword').value = '';

    const list = document.getElementById('editUserCoursesList');
    list.innerHTML = state.adminCourses.map((c) => {
        const checked = user.course_ids.includes(c.id) ? 'checked' : '';
        return `
            <label class="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" name="editUserCourse" value="${escapeHtml(c.id)}" ${checked}>
                <span>${escapeHtml(c.title)}</span>
            </label>
        `;
    }).join('');

    document.getElementById('userEditModal').classList.remove('hidden');
}

function closeUserEditModal() {
    state.editingUserId = null;
    document.getElementById('userEditModal').classList.add('hidden');
}

async function saveUserEdit() {
    const userId = state.editingUserId;
    if (!userId) return;

    const display_name = document.getElementById('editDisplayName').value.trim();
    const role = document.getElementById('editRole').value;
    const active = document.getElementById('editActive').value === 'true';
    const newPassword = document.getElementById('editNewPassword').value;
    const course_ids = [...document.querySelectorAll('input[name="editUserCourse"]:checked')].map((el) => el.value);

    try {
        await api(`/api/admin/users/${userId}`, {
            method: 'PUT',
            body: JSON.stringify({ display_name, role, active }),
        });
        await api(`/api/admin/users/${userId}/courses`, {
            method: 'PUT',
            body: JSON.stringify({ course_ids }),
        });
        if (newPassword) {
            await api(`/api/admin/users/${userId}/reset-password`, {
                method: 'POST',
                body: JSON.stringify({ password: newPassword }),
            });
        }
        closeUserEditModal();
        showToast('Usuário atualizado', 'Alterações salvas.', 'green');
        await loadAdminUsersAndCourses();
    } catch (err) {
        showToast('Erro', err.message, 'rose');
    }
}

// ---------------- IMPORTAÇÃO MARKDOWN (.MD) ----------------

function handleMdFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('mdInput').value = e.target.result;
        previewMdImport();
    };
    reader.readAsText(file);
    event.target.value = '';
}

async function previewMdImport() {
    const markdown = document.getElementById('mdInput').value;
    const box = document.getElementById('mdPreviewBox');
    const confirmBtn = document.getElementById('confirmImportBtn');
    box.classList.remove('hidden');

    try {
        const res = await api('/api/admin/courses/preview-md', {
            method: 'POST',
            body: JSON.stringify({ markdown }),
        });
        state.mdPreviewValid = res.valid;

        if (!res.valid) {
            confirmBtn.classList.add('hidden');
            box.innerHTML = `
                <div class="bg-red-50 border border-red-200 text-red-800 rounded-lg p-3 space-y-1">
                    <div class="font-bold">Erros encontrados na validação:</div>
                    <ul class="list-disc pl-4 space-y-0.5">${res.errors.map((e) => `<li>${escapeHtml(e)}</li>`).join('')}</ul>
                </div>
            `;
            return;
        }

        const c = res.course;
        const s = c.stats;
        const usersChecks = state.adminUsers
            .filter((u) => u.role !== 'admin')
            .map((u) => `
                <label class="inline-flex items-center gap-1.5 cursor-pointer">
                    <input type="checkbox" name="importGrantUser" value="${u.id}">
                    <span>${escapeHtml(u.display_name)} (@${escapeHtml(u.username)})</span>
                </label>
            `).join('');

        confirmBtn.classList.remove('hidden');
        box.innerHTML = `
            <div class="bg-emerald-50/70 border border-emerald-200 rounded-lg p-3.5 space-y-2">
                <div class="flex flex-wrap items-center justify-between gap-2">
                    <div class="font-bold text-ink">${escapeHtml(c.title)} <span class="font-mono text-[11px] text-muted">(${escapeHtml(c.id)})</span></div>
                    <span class="px-2 py-0.5 rounded text-[11px] font-medium ${res.isUpdate ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}">
                        ${res.isUpdate ? 'Atualização (preserva progresso)' : 'Novo curso'}
                    </span>
                </div>
                <div class="text-muted">${escapeHtml(c.description)}</div>
                <div class="font-mono text-[11px] text-ink flex flex-wrap gap-4 pt-1">
                    <span>${s.paths_count} trilhas</span>
                    <span>${s.modules_count} módulos</span>
                    <span>${s.units_count} unidades</span>
                    <span>${s.total_xp} XP total</span>
                    <span>${s.trophies_count} conquistas</span>
                </div>
                ${usersChecks ? `<div class="pt-2 border-t border-emerald-200/70 flex flex-wrap items-center gap-3"><span class="font-medium text-ink">Liberar para:</span>${usersChecks}</div>` : ''}
            </div>
        `;
    } catch (err) {
        confirmBtn.classList.add('hidden');
        box.innerHTML = `<div class="text-red-700">${escapeHtml(err.message)}</div>`;
    }
}

async function confirmMdImport() {
    if (!state.mdPreviewValid) return;
    const markdown = document.getElementById('mdInput').value;
    const grant_user_ids = [...document.querySelectorAll('input[name="importGrantUser"]:checked')].map((el) => Number(el.value));

    try {
        const res = await api('/api/admin/courses/import-md', {
            method: 'POST',
            body: JSON.stringify({ markdown, grant_user_ids }),
        });
        document.getElementById('confirmImportBtn').classList.add('hidden');
        document.getElementById('mdPreviewBox').classList.add('hidden');
        document.getElementById('mdInput').value = '';
        showToast(res.updated ? 'Curso atualizado' : 'Curso importado', res.course.title, 'green');
        await loadAdminUsersAndCourses();
    } catch (err) {
        showToast('Erro', err.message, 'rose');
    }
}

function renderAdminCoursesList() {
    const container = document.getElementById('adminCoursesList');
    container.innerHTML = state.adminCourses.map((c) => `
        <div class="px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
            <div>
                <div class="font-bold text-ink dark:text-zinc-100">${escapeHtml(c.title)} <span class="font-mono text-[11px] text-muted dark:text-zinc-400">(${escapeHtml(c.id)})</span></div>
                <div class="text-muted dark:text-zinc-400 font-mono text-[11px]">${c.stats?.modules_count || 0} módulos • ${c.stats?.units_count || 0} unidades • ${c.stats?.total_xp || 0} XP • ${c.access_count} aluno(s)</div>
            </div>
            <div class="flex items-center gap-2">
                <button type="button" onclick="toggleCourseActive('${escapeHtml(c.id)}', ${!c.active})" class="px-2.5 py-1 rounded border border-line dark:border-zinc-700 ${c.active ? 'bg-emerald-50 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400'} font-medium">
                    ${c.active ? 'Ativo' : 'Inativo'}
                </button>
            </div>
        </div>
    `).join('');
}

async function toggleCourseActive(courseId, active) {
    try {
        await api(`/api/admin/courses/${encodeURIComponent(courseId)}`, {
            method: 'PATCH',
            body: JSON.stringify({ active }),
        });
        showToast('Curso atualizado', active ? 'Curso ativado.' : 'Curso desativado.', 'blue');
        await loadAdminUsersAndCourses();
    } catch (err) {
        showToast('Erro', err.message, 'rose');
    }
}

async function loadAdminProgress() {
    const container = document.getElementById('adminProgressContainer');
    try {
        const res = await api('/api/admin/progress');
        const list = res.overview || [];
        container.innerHTML = list.map((u) => `
            <div class="bg-surface dark:bg-[#181A1F] border border-line dark:border-zinc-800 rounded-xl p-4 space-y-2.5">
                <div class="flex items-center justify-between">
                    <div>
                        <span class="font-bold text-sm text-ink dark:text-zinc-100">${escapeHtml(u.display_name)}</span>
                        <span class="font-mono text-xs text-muted dark:text-zinc-400 ml-1.5">@${escapeHtml(u.username)}</span>
                    </div>
                    <span class="text-[11px] font-mono px-2 py-0.5 rounded ${u.active ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300' : 'bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-400'}">${u.active ? 'Ativo' : 'Desativado'}</span>
                </div>
                ${u.courses.length ? `
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                        ${u.courses.map((c) => `
                            <div class="bg-paper dark:bg-zinc-900 border border-line dark:border-zinc-800 rounded-lg p-3 text-xs space-y-1">
                                <div class="font-semibold text-ink dark:text-zinc-100">${escapeHtml(c.course_title)}</div>
                                <div class="font-mono text-[11px] text-muted dark:text-zinc-400 tabular-nums">
                                    ${c.percent}% • ${c.completedModules}/${c.totalModules} módulos • ${c.xp} XP (Nv ${c.level}) • ${c.unlockedTrophies}/${c.totalTrophies} conquistas
                                </div>
                            </div>
                        `).join('')}
                    </div>
                ` : '<div class="text-xs text-muted dark:text-zinc-400">Nenhum curso liberado para este usuário.</div>'}
            </div>
        `).join('');
    } catch (err) {
        showToast('Erro', err.message, 'rose');
    }
}

// ---------------- TOAST ----------------

function showToast(title, desc, type = 'green') {
    const toast = document.getElementById('toast');
    const iconBox = document.getElementById('toastIcon');
    document.getElementById('toastTitle').innerText = title;
    document.getElementById('toastDesc').innerText = desc;

    if (type === 'rose') {
        iconBox.className = 'w-7 h-7 rounded-md bg-red-500/20 text-red-400 flex items-center justify-center text-xs shrink-0';
        iconBox.innerHTML = '<i class="fa-solid fa-xmark"></i>';
    } else if (type === 'blue') {
        iconBox.className = 'w-7 h-7 rounded-md bg-zinc-700 text-zinc-200 flex items-center justify-center text-xs shrink-0';
        iconBox.innerHTML = '<i class="fa-solid fa-info"></i>';
    } else {
        iconBox.className = 'w-7 h-7 rounded-md bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-xs shrink-0';
        iconBox.innerHTML = '<i class="fa-solid fa-check"></i>';
    }

    toast.classList.remove('translate-y-24', 'opacity-0');
    if (state.toastTimer) clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => {
        toast.classList.add('translate-y-24', 'opacity-0');
    }, 3000);
}
