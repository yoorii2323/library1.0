const API_BASE = '/api';
let currentLang = localStorage.getItem('lang') || 'ru';

const I18N = {
    ru: {
        title: '📚 Цифровой каталог библиотеки',
        subtitle: 'Система полнотекстового поиска литературы',
        navHome: 'На главную',
        navPopular: 'Популярные',
        navFavorites: 'Избранное',
        navSearch: 'Поиск',
        genre: 'Жанр:',
        allGenres: 'Все жанры',
        source: 'Источник:',
        sourceAll: 'Все источники',
        yearFrom: 'Год от:',
        yearTo: 'Год до:',
        searchBtn: 'Найти',
        clearFilters: 'Очистить фильтры',
        results: 'Результаты поиска',
        found: (n) => `Найдено книг: ${n}`,
        emptyTitle: 'Начните поиск',
        emptyDesc: 'Введите запрос в поле поиска, чтобы найти интересующие вас книги',
        emptyAlt: 'Попробуйте изменить поисковый запрос или фильтры',
        prev: '← Предыдущая',
        next: 'Следующая →',
        popularTitle: 'Популярные книги',
        popularSubtitle: 'Тренды недели',
        more: 'Подробнее →',
        errorNoQuery: 'Введите поисковый запрос или выберите жанр',
        errorSearch: 'Ошибка при выполнении поиска. Убедитесь, что сервер запущен.',
        similarResults: 'Похожие результаты'
    },
    en: {
        title: '📚 Digital Library Catalog',
        subtitle: 'Full-text literature search system',
        navHome: 'Home',
        navPopular: 'Popular',
        navFavorites: 'Favorites',
        navSearch: 'Search',
        genre: 'Genre:',
        allGenres: 'All genres',
        source: 'Source:',
        sourceAll: 'All sources',
        yearFrom: 'Year from:',
        yearTo: 'Year to:',
        searchBtn: 'Search',
        clearFilters: 'Clear filters',
        results: 'Search results',
        found: (n) => `Books found: ${n}`,
        emptyTitle: 'Start searching',
        emptyDesc: 'Type your query to find interesting books',
        emptyAlt: 'Try changing your query or filters',
        prev: '← Previous',
        next: 'Next →',
        popularTitle: 'Popular books',
        popularSubtitle: 'Trending this week',
        more: 'More →',
        errorNoQuery: 'Enter a query or choose a genre',
        errorSearch: 'Search failed. Make sure the server is running.',
        similarResults: 'Similar results'
    }
};

let currentPage = 1;
let currentQuery = '';
let currentFilters = {
    genre: '',
    yearFrom: '',
    yearTo: ''
};
let currentSource = 'openlibrary';

const GENRE_MAP = {
    'Fantasy': 'Фэнтези',
    'Science fiction': 'Научная фантастика',
    'Romance': 'Роман',
    'Mystery': 'Детектив',
    'Thriller': 'Триллер',
    'Horror': 'Ужасы',
    'History': 'История',
    'Biography': 'Биография',
    'Poetry': 'Поэзия',
    "Children's literature": 'Детская литература',
    'Young Adult': 'Подростковая литература',
    'Philosophy': 'Философия',
    'Psychology': 'Психология',
    'Technology': 'Технологии',
    'Computer science': 'Информатика'
};

function translateGenre(name) {
    if (!name) return '';
    const first = String(name).split(',')[0].trim();
    if (currentLang === 'ru') {
        if (/[\u0400-\u04FF]/.test(first)) return first;
        if (GENRE_MAP[first]) return GENRE_MAP[first];
        const key = Object.keys(GENRE_MAP).find(k => k.toLowerCase() === first.toLowerCase());
        return key ? GENRE_MAP[key] : first;
    }
    return first;
}

let currentUser = null;

document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    loadGenres();
    loadTopBooks();
    initLangSwitcher();
    applyTranslations();
    checkUserAuth();
    document.querySelectorAll('a[href^="#"]').forEach(link => {
        link.addEventListener('click', (e) => {
            const targetId = link.getAttribute('href');
            if (targetId.length > 1) {
                e.preventDefault();
                const el = document.querySelector(targetId);
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth' });
                }
            }
        });
    });
});

async function checkUserAuth() {
    try {
        const response = await fetch(`${API_BASE}/user`, {
            credentials: 'include'
        });
        const data = await response.json();
        
        if (data.user) {
            currentUser = data.user;
            const registerBtn = document.getElementById('registerBtn');
            const profileBtn = document.getElementById('profileBtn');
            const navFav = document.getElementById('navFavorites');
            if (registerBtn) registerBtn.style.display = 'none';
            if (profileBtn) profileBtn.style.display = 'inline-block';
            if (navFav) navFav.style.display = 'inline-block';
        } else {
            currentUser = null;
            const registerBtn = document.getElementById('registerBtn');
            const profileBtn = document.getElementById('profileBtn');
            const navFav = document.getElementById('navFavorites');
            if (registerBtn) registerBtn.style.display = 'inline-block';
            if (profileBtn) profileBtn.style.display = 'none';
            if (navFav) navFav.style.display = 'none';
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        currentUser = null;
        const navFav = document.getElementById('navFavorites');
        if (navFav) navFav.style.display = 'none';
    }
}

function t(key, ...args) {
    const v = I18N[currentLang][key];
    return typeof v === 'function' ? v(...args) : v;
}

function initLangSwitcher() {
    const select = document.getElementById('langSelect');
    if (!select) return;
    select.value = currentLang;
    select.addEventListener('change', () => {
        currentLang = select.value;
        localStorage.setItem('lang', currentLang);
        applyTranslations();
        const navFav = document.getElementById('navFavorites');
        if (navFav) navFav.style.display = currentUser ? 'inline-block' : 'none';
        // Перевести подписи жанров в выпадающем списке
        const genreSelect = document.getElementById('genreFilter');
        Array.from(genreSelect.options).forEach(opt => {
            if (opt.value === '') {
                opt.textContent = t('allGenres');
            } else {
                opt.textContent = translateGenre(opt.value);
            }
        });
        // Перерисовать результаты (бейдж жанра)
        if (document.getElementById('booksGrid').children.length > 0) {
            // Тригерим обновление DOM через повторный рендер текущей страницы
            if (currentQuery || currentFilters.genre) {
                performSearch();
            }
        }
    });
}

function applyTranslations() {
    const searchBtnLabel = document.getElementById('searchBtnLabel');
    if (searchBtnLabel) {
        searchBtnLabel.textContent = ' ' + t('searchBtn');
    }

    const clearBtn = document.getElementById('clearFilters');
    if (clearBtn) clearBtn.textContent = t('clearFilters');

    const searchInput = document.getElementById('searchInput');
    if (searchInput) searchInput.placeholder = currentLang === 'ru'
        ? 'Введите название книги, автора, жанр или любую фразу для поиска...'
        : 'Enter a book title, author, genre or any phrase...';

    // Простые тексты
    const mapping = {
        titleText: t('title'),
        subtitleText: t('subtitle'),
        navHome: t('navHome'),
        navPopular: t('navPopular'),
        navFavorites: t('navFavorites'),
        navSearch: t('navSearch'),
        genreLabel: t('genre'),
        allGenresOption: t('allGenres'),
        sourceLabel: t('source'),
        sourceAll: t('sourceAll'),
        yearFromLabel: t('yearFrom'),
        yearToLabel: t('yearTo'),
        popularTitle: t('popularTitle'),
        popularSubtitle: t('popularSubtitle'),
        footerTitle: currentLang === 'ru' ? 'Цифровой каталог библиотеки © 2024' : 'Digital Library Catalog © 2024',
        footerSubtitle: currentLang === 'ru' ? 'Использует Open Library API для получения данных' : 'Powered by Open Library API'
    };
    Object.entries(mapping).forEach(([id, text]) => {
        const el = document.getElementById(id);
        if (el && typeof text === 'string') el.textContent = text;
    });
}

// Инициализация обработчиков событий
function initEventListeners() {
    const searchForm = document.getElementById('searchForm');
    const clearFiltersBtn = document.getElementById('clearFilters');
    
    searchForm.addEventListener('submit', handleSearch);
    clearFiltersBtn.addEventListener('click', clearFilters);
    
    // Поиск при изменении фильтров
    document.getElementById('genreFilter').addEventListener('change', applyFilters);
    document.getElementById('yearFrom').addEventListener('change', applyFilters);
    document.getElementById('yearTo').addEventListener('change', applyFilters);
    const sourceSelect = document.getElementById('sourceSelect');
    if (sourceSelect) {
        sourceSelect.addEventListener('change', () => {
            currentSource = sourceSelect.value;
        });
    }
}

// Загрузка списка жанров
async function loadGenres() {
    try {
        const response = await fetch(`${API_BASE}/genres`);
        const data = await response.json();
        const genreSelect = document.getElementById('genreFilter');

        // Добавляем жанры из локальной БД (если есть)
        if (data && Array.isArray(data.genres)) {
            data.genres.forEach(genre => {
                const option = document.createElement('option');
                option.value = genre;
                option.textContent = translateGenre(genre);
                genreSelect.appendChild(option);
            });
        }

        // Базовые жанры для Open Library (EN subjects для корректного совпадения)
        const DEFAULT_SUBJECTS = [
            'Fantasy',
            'Science fiction',
            'Romance',
            'Mystery',
            'Thriller',
            'Horror',
            'History',
            'Biography',
            'Poetry',
            "Children's literature",
            'Young Adult',
            'Philosophy',
            'Psychology',
            'Technology',
            'Computer science'
        ];

        const existing = new Set(Array.from(genreSelect.options).map(o => o.value.toLowerCase()));
        DEFAULT_SUBJECTS.forEach(subj => {
            if (!existing.has(subj.toLowerCase())) {
                const option = document.createElement('option');
                option.value = subj;
                option.textContent = translateGenre(subj);
                genreSelect.appendChild(option);
            }
        });
    } catch (error) {
        console.error('Ошибка при загрузке жанров:', error);
    }
}

// Загрузка популярных книг (топ-6)
async function loadTopBooks() {
    const grid = document.getElementById('topBooksGrid');
    if (!grid) return;

    // 1) Моментально показываем последние локальные книги (быстро)
    let hasLocalBooks = false;
    try {
        const recent = await fetchJsonWithTimeout(`${API_BASE}/books?per_page=6&page=1`, 1500);
        if (recent && Array.isArray(recent.books) && recent.books.length > 0) {
            grid.innerHTML = '';
            recent.books.forEach(book => grid.appendChild(createBookCard(book)));
            hasLocalBooks = true;
        }
    } catch (_) {}

    // 2) Параллельно пытаемся получить тренды и заменить контент, если успеют
    // Если локальных книг нет, этот запрос обязателен (бэкенд гарантирует результат)
    try {
        const trending = await fetchJsonWithTimeout(`${API_BASE}/openlibrary/top?limit=6`, hasLocalBooks ? 2500 : 4000);
        if (trending && Array.isArray(trending.books) && trending.books.length > 0) {
            grid.innerHTML = '';
            trending.books.forEach(book => grid.appendChild(createBookCard(book)));
        }
    } catch (_) {
        // Если даже это не сработало, пробуем еще раз через обычный поиск
        if (!hasLocalBooks && grid.children.length === 0) {
            try {
                const fallback = await fetchJsonWithTimeout(`${API_BASE}/openlibrary/search?q=fiction&per_page=6&page=1`, 3000);
                if (fallback && Array.isArray(fallback.books) && fallback.books.length > 0) {
                    grid.innerHTML = '';
                    fallback.books.forEach(book => grid.appendChild(createBookCard(book)));
                }
            } catch (_) {}
        }
    }
}

// Обработка поискового запроса
async function handleSearch(e) {
    e.preventDefault();
    
    const searchInput = document.getElementById('searchInput');
    const query = searchInput.value.trim();
    
    if (!query && !document.getElementById('genreFilter').value) {
        showError(t('errorNoQuery'));
        return;
    }
    
    currentQuery = query;
    currentPage = 1;
    await performSearch();
}

// Выполнение поиска
async function performSearch() {
    showLoading();
    hideError();
    hideEmptyState();
    
    try {
        let response;
        if (currentQuery) {
            const params = new URLSearchParams({
                q: currentQuery,
                page: currentPage,
                per_page: 20
            });
            // Для OpenLibrary жанр должен быть на английском —
            // если выбран жанр на кириллице, игнорируем фильтр жанра
            if (currentFilters.genre && !(/[\u0400-\u04FF]/.test(currentFilters.genre))) {
                params.append('genre', currentFilters.genre);
            }
            if (currentFilters.yearFrom) params.append('year_from', currentFilters.yearFrom);
            if (currentFilters.yearTo) params.append('year_to', currentFilters.yearTo);
            // Выбор источника
            let endpoint = '/openlibrary/search';
            if (currentSource === 'gutendex') endpoint = '/gutendex/search';
            if (currentSource === 'knigafund') endpoint = '/knigafund/search';
            if (currentSource === 'aggregate') endpoint = '/search/aggregate';
            response = await fetch(`${API_BASE}${endpoint}?${params}`);
        } else if (currentFilters.genre) {
            const params = new URLSearchParams({
                page: currentPage,
                per_page: 20,
                genre: currentFilters.genre
            });
            response = await fetch(`${API_BASE}/books?${params}`);
        }
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        hideLoading();
        
        if (data.books && data.books.length > 0) {
            displayResults(data);
        } else {
            // Пытаемся найти похожие результаты
            const fallback = await performFallbackSearch();
            if (fallback && fallback.books && fallback.books.length > 0) {
                // помечаем как похожие
                displayResults({ ...fallback, labelSimilar: true });
            } else {
                showEmptyState(currentLang === 'ru' ? 'По вашему запросу ничего не найдено' : 'No results found');
            }
        }
        
    } catch (error) {
        console.error('Ошибка поиска:', error);
        hideLoading();
        showError(t('errorSearch'));
    }
}

// Fallback-стратегия при отсутствии точных результатов
async function performFallbackSearch() {
    try {
        if (!currentQuery) return null;

        const perPage = 12; // меньше элементов — быстрее ответ и рендер
        const base = new URLSearchParams({ q: currentQuery, page: 1, per_page: perPage });
        if (currentFilters.yearFrom) base.append('year_from', currentFilters.yearFrom);
        if (currentFilters.yearTo) base.append('year_to', currentFilters.yearTo);
        if (currentFilters.genre && !(/[\u0400-\u04FF]/.test(currentFilters.genre))) {
            base.append('genre', currentFilters.genre);
        }

        // формируем набор быстрых параллельных попыток и берём первую удачную
        const tasks = [];

        // 1) текущий источник без жанра (если жанр мог тормозить)
        const noGenre = new URLSearchParams(base);
        noGenre.delete('genre');
        let endpoint = currentSource === 'googlebooks' ? '/googlebooks/search'
            : currentSource === 'gutendex' ? '/gutendex/search'
            : currentSource === 'aggregate' ? '/search/aggregate'
            : '/openlibrary/search';
        tasks.push(fastSearch(`${API_BASE}${endpoint}?${noGenre}`));

        // 2) Open Library — самый быстрый провайдер, без жанра
        tasks.push(fastSearch(`${API_BASE}/openlibrary/search?${noGenre}`));

        // 3) Агрегат без жанра, но с коротким таймаутом
        tasks.push(fastSearch(`${API_BASE}/search/aggregate?${noGenre}`, 4500));

        // 4) По двум самым длинным ключевым словам параллельно (ускоряет на узких запросах)
        const terms = currentQuery
            .split(/\s+/)
            .filter(t => t && t.length >= 3)
            .sort((a, b) => b.length - a.length)
            .slice(0, 2);
        for (const t of terms) {
            const p = new URLSearchParams({ q: t, page: 1, per_page: perPage });
            tasks.push(fastSearch(`${API_BASE}/openlibrary/search?${p}`, 3500));
        }

        // Берём первую вернувшуюся с непустым списком
        const firstOk = await firstResolved(tasks);
        if (firstOk) return firstOk;
    } catch (e) {
        console.warn('Fallback search failed:', e);
    }
    return null;
}

async function fetchJsonWithTimeout(url, timeoutMs) {
    const ctrl = new AbortController();
    const to = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
        const r = await fetch(url, { signal: ctrl.signal });
        if (!r.ok) return null;
        return await r.json();
    } catch (e) {
        return null;
    } finally {
        clearTimeout(to);
    }
}

function fastSearch(url, timeoutMs = 4000) {
    return (async () => {
        const data = await fetchJsonWithTimeout(url, timeoutMs);
        if (data && Array.isArray(data.books) && data.books.length > 0) return data;
        throw new Error('empty');
    })();
}

async function firstResolved(promises) {
    return Promise.any(promises).catch(() => null);
}

// Отображение результатов
function displayResults(data) {
    const resultsSection = document.getElementById('resultsSection');
    const booksGrid = document.getElementById('booksGrid');
    const resultsTitle = document.getElementById('resultsTitle');
    const resultsCount = document.getElementById('resultsCount');
    
    resultsSection.classList.remove('hidden');
    booksGrid.innerHTML = '';
    
    // Обновление заголовка и счетчика
    const baseTitle = currentQuery ? `${t('results')}: "${currentQuery}"` : t('results');
    resultsTitle.textContent = data.labelSimilar ? `${baseTitle} — ${t('similarResults')}` : baseTitle;
    resultsCount.textContent = (I18N[currentLang].found)(data.total);
    
    // Отображение книг
    data.books.forEach(book => {
        const bookCard = createBookCard(book);
        booksGrid.appendChild(bookCard);
    });
    
    // Отображение пагинации
    if (data.pages > 1) {
        displayPagination(data);
    } else {
        document.getElementById('pagination').innerHTML = '';
    }
}

// Создание карточки книги
function createBookCard(book) {
    const card = document.createElement('div');
    card.className = 'book-card';
    
    const cover = book.cover_url 
        ? `<img src="${book.cover_url}" alt="${book.title}" class="book-cover" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />`
        : '';
    
    const coverFallbackStyle = 'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); align-items: center; justify-content: center; color: white; font-size: 48px;';
    const placeholder = `<div class="book-cover" style="${book.cover_url ? 'display: none; ' : 'display: flex; '}${coverFallbackStyle}">📚</div>`;
    
    const bookData = {
        title: book.title || '',
        author: book.author || '',
        cover_url: book.cover_url || '',
        source_url: book.source_url || '',
        year: book.year || null,
        genre: book.genre || ''
    };
    
    const favoriteBtn = currentUser 
        ? `<button class="favorite-btn" data-book='${JSON.stringify(bookData)}' onclick="event.stopPropagation(); addToFavoritesFromButton(this)" style="margin-top: 10px; padding: 8px 15px; background: var(--secondary-color); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9em; width: 100%;">⭐ В избранное</button>`
        : `<button class="favorite-btn" onclick="event.stopPropagation(); promptRegister()" style="margin-top: 10px; padding: 8px 15px; background: var(--secondary-color); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9em; width: 100%;">⭐ В избранное</button>`;
    
    card.innerHTML = `
        ${cover}
        ${placeholder}
        <div class="book-title">${escapeHtml(book.title || 'Без названия')}</div>
        <div class="book-author">${escapeHtml(book.author || 'Неизвестный автор')}</div>
        <div class="book-meta">
            ${book.year ? `<span>📅 ${book.year}</span>` : ''}
        </div>
        ${book.genre ? `<span class="book-genre">${escapeHtml(translateGenre(book.genre))}</span>` : ''}
        ${book.description ? `<div class="book-description">${escapeHtml(book.description.substring(0, 150))}...</div>` : ''}
        ${favoriteBtn}
        ${book.source_url ? `<a href="${book.source_url}" target="_blank" onclick="event.stopPropagation();" style="margin-top: 10px; color: var(--primary-color); text-decoration: none; font-size: 0.9em; display: block;">Подробнее →</a>` : ''}
    `;
    
    // Добавление обработчика клика (только если есть source_url и не кликнули на кнопку)
    if (book.source_url) {
        card.addEventListener('click', (e) => {
            // Не открываем ссылку, если кликнули на кнопку или ссылку
            if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A') {
                return;
            }
            window.open(book.source_url, '_blank');
        });
    }
    
    return card;
}

// Добавление в избранное (из кнопки)
function addToFavoritesFromButton(button) {
    const bookData = JSON.parse(button.getAttribute('data-book'));
    addToFavorites(bookData);
}

// Добавление в избранное
async function addToFavorites(book) {
    if (!currentUser) {
        promptRegister();
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/favorites`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                book_title: book.title || '',
                book_author: book.author || '',
                book_cover_url: book.cover_url || '',
                book_source_url: book.source_url || '',
                book_year: book.year || null,
                book_genre: book.genre || '',
                status: 'favorite'
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            if (data.error.includes('Authentication required')) {
                promptRegister();
            } else {
                alert('Ошибка: ' + data.error);
            }
            return;
        }
        
        alert('Книга добавлена в избранное!');
    } catch (error) {
        console.error('Failed to add favorite:', error);
        alert('Ошибка соединения с сервером');
    }
}

// Предложение зарегистрироваться
function promptRegister() {
    if (confirm('Для добавления книг в избранное необходимо зарегистрироваться. Перейти на страницу регистрации?')) {
        window.location.href = '/register';
    }
}

// Отображение пагинации
function displayPagination(data) {
    const pagination = document.getElementById('pagination');
    pagination.innerHTML = '';
    
    const maxPages = Math.min(data.pages, 10);
    const startPage = Math.max(1, currentPage - 5);
    const endPage = Math.min(data.pages, startPage + maxPages - 1);
    
    // Кнопка "Предыдущая"
    const prevBtn = document.createElement('button');
    prevBtn.textContent = t('prev');
    prevBtn.disabled = currentPage === 1;
    prevBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            performSearch();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });
    pagination.appendChild(prevBtn);
    
    // Номера страниц
    for (let i = startPage; i <= endPage; i++) {
        const pageBtn = document.createElement('button');
        pageBtn.textContent = i;
        pageBtn.className = i === currentPage ? 'active' : '';
        pageBtn.addEventListener('click', () => {
            currentPage = i;
            performSearch();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
        pagination.appendChild(pageBtn);
    }
    
    // Кнопка "Следующая"
    const nextBtn = document.createElement('button');
    nextBtn.textContent = t('next');
    nextBtn.disabled = currentPage === data.pages;
    nextBtn.addEventListener('click', () => {
        if (currentPage < data.pages) {
            currentPage++;
            performSearch();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });
    pagination.appendChild(nextBtn);
}

// Применение фильтров
function applyFilters() {
    if (!currentQuery) return;
    
    currentFilters = {
        genre: document.getElementById('genreFilter').value,
        yearFrom: document.getElementById('yearFrom').value,
        yearTo: document.getElementById('yearTo').value
    };
    
    currentPage = 1;
    performSearch();
}

// Очистка фильтров
function clearFilters() {
    document.getElementById('genreFilter').value = '';
    document.getElementById('yearFrom').value = '';
    document.getElementById('yearTo').value = '';
    
    currentFilters = {
        genre: '',
        yearFrom: '',
        yearTo: ''
    };
    
    if (currentQuery) {
        currentPage = 1;
        performSearch();
    }
}

// Показать загрузку
function showLoading() {
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('resultsSection').classList.add('hidden');
    document.getElementById('emptyState').classList.add('hidden');
}

// Скрыть загрузку
function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

// Показать пустое состояние
function showEmptyState(message) {
    const emptyState = document.getElementById('emptyState');
    emptyState.classList.remove('hidden');
    emptyState.querySelector('h3').textContent = message || 'Начните поиск';
    emptyState.querySelector('p').textContent = message 
        ? 'Попробуйте изменить поисковый запрос или фильтры'
        : 'Введите запрос в поле поиска, чтобы найти интересующие вас книги';
    
    document.getElementById('resultsSection').classList.add('hidden');
}

// Скрыть пустое состояние
function hideEmptyState() {
    document.getElementById('emptyState').classList.add('hidden');
}

// Показать ошибку
function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
    
    setTimeout(() => {
        errorDiv.classList.add('hidden');
    }, 5000);
}

// Скрыть ошибку
function hideError() {
    document.getElementById('errorMessage').classList.add('hidden');
}

// Экранирование HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

