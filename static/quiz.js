/* ── UmkaHub — квиз подбора кружков/секций ────────────────────────────────
   Один модуль, два места использования: /orgs/quiz (отдельный лендинг под
   платный трафик) и оверлей поверх /orgs (баннер "быстрый подбор").
   Район НЕ используется как жёсткий фильтр — только мягкая сортировка. */

(function () {
  const CATEGORIES = ['IT', 'языки', 'творчество', 'спорт', 'развитие'];
  const CAT_LABELS = { IT: 'IT', 'языки': 'Языки', 'творчество': 'Творчество', 'спорт': 'Спорт', 'развитие': 'Развитие' };
  const CAT_BG = {
    'IT':         'linear-gradient(135deg,#EEF2FF,#C7D2FE)',
    'спорт':      'linear-gradient(135deg,#ECFDF5,#A7F3D0)',
    'творчество': 'linear-gradient(135deg,#FFFBEB,#FDE68A)',
    'языки':      'linear-gradient(135deg,#EFF6FF,#BFDBFE)',
    'развитие':   'linear-gradient(135deg,#F5F3FF,#DDD6FE)',
  };
  const BUDGETS = [
    { label: 'До 3 000 ₽/мес', val: 3000 },
    { label: 'До 6 000 ₽/мес', val: 6000 },
    { label: 'До 10 000 ₽/мес', val: 10000 },
    { label: 'Неважно', val: null },
  ];
  const AGE_PRESETS = [5, 7, 9, 11, 13];

  function esc(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function initials(name) {
    return (name || '').split(/[\s«»""]+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');
  }
  function formatPrice(org) {
    if (org.price_from) {
      const lo = org.price_from.toLocaleString('ru-RU');
      return `от ${lo} ₽`;
    }
    if (org.price) return esc(org.price);
    return 'цена по запросу';
  }

  function resultCardHTML(org) {
    const bg = CAT_BG[org.category] || 'linear-gradient(135deg,#F0F9FF,#E0F2FE)';
    const ini = initials(org.name);
    return `
      <a class="quiz-result-card" href="/org/${org.id}" target="_blank" rel="noopener">
        <div class="quiz-result-photo" style="background:${bg}">
          <span class="quiz-result-initials">${ini}</span>
        </div>
        <div class="quiz-result-body">
          <span class="quiz-result-cat">${esc(CAT_LABELS[org.category] || org.category)}</span>
          <div class="quiz-result-name">${esc(org.name)}</div>
          <div class="quiz-result-meta">${org.metro ? esc(org.metro) + ' · ' : ''}${esc(org.age_range || '')}</div>
          <div class="quiz-result-price">${formatPrice(org)}</div>
        </div>
      </a>`;
  }

  // Merge results from multiple category queries, dedupe by id, keep API's
  // own ordering (featured -> data_quality -> rating, already applied
  // server-side per query) via a stable client-side re-sort on those same
  // fields, then soft-boost district matches without excluding anyone else.
  function mergeAndRank(lists, district) {
    const seen = new Map();
    lists.flat().forEach(o => { if (!seen.has(o.id)) seen.set(o.id, o); });
    let items = Array.from(seen.values());
    const districtLower = (district || '').trim().toLowerCase();
    items.sort((a, b) => {
      if (districtLower) {
        const aNear = (a.metro || '').toLowerCase().includes(districtLower) ? 1 : 0;
        const bNear = (b.metro || '').toLowerCase().includes(districtLower) ? 1 : 0;
        if (aNear !== bNear) return bNear - aNear;
      }
      if ((b.featured ? 1 : 0) !== (a.featured ? 1 : 0)) return (b.featured ? 1 : 0) - (a.featured ? 1 : 0);
      if ((b.data_quality || 0) !== (a.data_quality || 0)) return (b.data_quality || 0) - (a.data_quality || 0);
      return (b.rating || 0) - (a.rating || 0);
    });
    return items.slice(0, 5);
  }

  function UmkaQuiz(container, opts) {
    opts = opts || {};
    const state = { step: 1, age: null, categories: [], price_max: undefined, district: '', results: null };

    render();

    function render() {
      container.innerHTML = shellHTML();
      bindShell();
    }

    function shellHTML() {
      const totalSteps = 4;
      const progress = Math.min(state.step, totalSteps);
      return `
        <div class="uq-progress"><div class="uq-progress-bar" style="width:${(progress / totalSteps) * 100}%"></div></div>
        <div class="uq-body">${stepHTML()}</div>`;
    }

    function stepHTML() {
      if (state.step === 1) return stepAge();
      if (state.step === 2) return stepCategory();
      if (state.step === 3) return stepBudget();
      if (state.step === 4) return stepDistrict();
      if (state.step === 'loading') return `<div class="uq-loading">Подбираем варианты…</div>`;
      if (state.step === 'results') return stepResults();
      return '';
    }

    function stepAge() {
      return `
        <div class="uq-q">Сколько лет ребёнку?</div>
        <div class="uq-presets">
          ${AGE_PRESETS.map(a => `<button class="uq-chip" data-age="${a}">${a}</button>`).join('')}
        </div>
        <input class="uq-input" type="number" min="2" max="18" placeholder="Или впишите возраст" id="uqAgeInput" value="${state.age || ''}">
        <button class="uq-next" id="uqNext1" ${state.age ? '' : 'disabled'}>Далее →</button>`;
    }

    function stepCategory() {
      return `
        <div class="uq-q">Что интересно ребёнку?</div>
        <div class="uq-hint">Можно выбрать несколько</div>
        <div class="uq-presets">
          ${CATEGORIES.map(c => `<button class="uq-chip ${state.categories.includes(c) ? 'active' : ''}" data-cat="${c}">${CAT_LABELS[c]}</button>`).join('')}
        </div>
        <button class="uq-next" id="uqNext2" ${state.categories.length ? '' : 'disabled'}>Далее →</button>`;
    }

    function stepBudget() {
      return `
        <div class="uq-q">Бюджет в месяц?</div>
        <div class="uq-presets uq-presets-col">
          ${BUDGETS.map((b, i) => `<button class="uq-chip uq-chip-wide" data-budget-idx="${i}">${b.label}</button>`).join('')}
        </div>`;
    }

    function stepDistrict() {
      return `
        <div class="uq-q">Район или город?</div>
        <div class="uq-hint">Необязательно — просто покажем ближайшие варианты выше в списке</div>
        <input class="uq-input" type="text" placeholder="Например, Люберцы или Юго-Западная" id="uqDistrictInput" value="${esc(state.district)}">
        <div class="uq-actions">
          <button class="uq-skip" id="uqSkip4">Пропустить</button>
          <button class="uq-next" id="uqNext4">Показать варианты →</button>
        </div>`;
    }

    function stepResults() {
      const items = state.results || [];
      const cards = items.length
        ? items.map(resultCardHTML).join('')
        : `<div class="uq-hint">Не нашли точных совпадений — попробуйте другие параметры (например, снимите ограничение по бюджету).</div>`;
      const header = items.length
        ? `<h3>Нашли ${items.length} подходящих вариантов</h3><p>Откройте карточку и оставьте заявку прямо у организации — так она увидит именно вашу заявку, не общий список.</p>`
        : `<h3>Пока пусто</h3>`;
      return `
        <div class="uq-success">${header}</div>
        <div class="uq-results-grid">${cards}</div>`;
    }

    function bindShell() {
      if (state.step === 1) {
        container.querySelectorAll('[data-age]').forEach(btn =>
          btn.addEventListener('click', () => { state.age = btn.dataset.age; render(); goto(2); }));
        const input = container.querySelector('#uqAgeInput');
        input.addEventListener('input', () => {
          state.age = input.value;
          container.querySelector('#uqNext1').disabled = !state.age;
        });
        container.querySelector('#uqNext1').addEventListener('click', () => goto(2));
      } else if (state.step === 2) {
        container.querySelectorAll('[data-cat]').forEach(btn =>
          btn.addEventListener('click', () => {
            const c = btn.dataset.cat;
            const idx = state.categories.indexOf(c);
            if (idx >= 0) state.categories.splice(idx, 1); else state.categories.push(c);
            render();
          }));
        const next = container.querySelector('#uqNext2');
        if (next) next.addEventListener('click', () => goto(3));
      } else if (state.step === 3) {
        container.querySelectorAll('[data-budget-idx]').forEach(btn =>
          btn.addEventListener('click', () => {
            state.price_max = BUDGETS[Number(btn.dataset.budgetIdx)].val;
            goto(4);
          }));
      } else if (state.step === 4) {
        const input = container.querySelector('#uqDistrictInput');
        container.querySelector('#uqSkip4').addEventListener('click', () => { state.district = ''; fireStep('district'); showResults(); });
        container.querySelector('#uqNext4').addEventListener('click', () => { state.district = input.value; fireStep('district'); showResults(); });
      }
    }

    // Funnel visibility per step, for Метрика's built-in funnel report —
    // fired on the step just COMPLETED, not the one being entered.
    const STEP_GOALS = { 2: 'age', 3: 'category', 4: 'budget' };
    function fireStep(name) {
      if (typeof ym !== 'undefined') ym(111728638, 'reachGoal', 'quiz_step_' + name);
    }
    function goto(step) {
      if (STEP_GOALS[step]) fireStep(STEP_GOALS[step]);
      state.step = step;
      render();
    }

    async function showResults() {
      state.step = 'loading'; render();

      try {
        const cats = state.categories.length ? state.categories : CATEGORIES;
        const queries = cats.map(cat => {
          const p = new URLSearchParams();
          p.set('category', cat);
          if (state.age) p.set('age', state.age);
          if (state.price_max) p.set('price_max', state.price_max);
          p.set('limit', '50');
          return fetch('/api/orgs?' + p.toString()).then(r => r.json()).then(d => d.items || []).catch(() => []);
        });
        const lists = await Promise.all(queries);
        state.results = mergeAndRank(lists, state.district);

        // Funnel-visibility signal only — NOT a lead. The real lead event
        // is `org_lead`, fired by org.html when someone actually submits a
        // form on a specific organization's page. Quiz is filter-only.
        if (typeof ym !== 'undefined') ym(111728638, 'reachGoal', 'quiz_orgs_results_shown');
      } catch (e) {
        state.results = [];
      }

      state.step = 'results';
      render();
      if (typeof opts.onDone === 'function') opts.onDone();
    }
  }

  window.UmkaQuiz = UmkaQuiz;
})();
