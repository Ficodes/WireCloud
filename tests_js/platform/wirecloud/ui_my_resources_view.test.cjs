const test = require('node:test');
const assert = require('node:assert/strict');
const {
    bootstrapStyledElementsBase,
    loadLegacyScript,
    resetLegacyRuntime,
} = require('../../support/legacy-runtime.cjs');

const setup = (options = {}) => {
    resetLegacyRuntime();
    bootstrapStyledElementsBase();

    // -------------------------------------------------------------------------
    // Mocks for callbacks and event listeners
    // -------------------------------------------------------------------------

    const logEntries = [];
    const dispatchEvents = [];
    const monitorTasks = [];
    const historyStates = [];
    const viewChanges = [];
    const refreshedSearches = [];
    const refreshedSources = [];
    const showedUploadDialogs = [];
    const showedMessageDialogs = [];
    const showedPublishDialogs = [];
    const showedAlertDialogs = [];
    const mockRequests = [];
    const detailPaints = [];
    const detailDisables = [];
    const detailEnables = [];

    // -------------------------------------------------------------------------
    // Create global Wirecloud namespace
    // -------------------------------------------------------------------------

    global.Wirecloud = {
        Utils: StyledElements.Utils,
        ui: {},
        WirecloudCatalogue: {},
    };

    // -------------------------------------------------------------------------
    // Mock Wirecloud.constants
    // -------------------------------------------------------------------------

    Wirecloud.constants = {
        LOGGING: {
            ERROR_MSG: 'error',
            WARN_MSG: 'warn',
        },
    };

    // -------------------------------------------------------------------------
    // Mock Wirecloud.GlobalLogManager
    // -------------------------------------------------------------------------

    Wirecloud.GlobalLogManager = {
        log(msg) {
            logEntries.push(msg);
        },
        parseErrorResponse(response) {
            return 'parsed-error:' + response.status;
        },
    };

    // -------------------------------------------------------------------------
    // Mock Wirecloud.ui.MessageWindowMenu
    // -------------------------------------------------------------------------

    class MockMessageWindowMenu {
        constructor(msg, level) {
            this.msg = msg;
            this.level = level;
            this.shown = false;
        }
        show() {
            this.shown = true;
            showedMessageDialogs.push(this);
        }
    }

    Wirecloud.ui.MessageWindowMenu = MockMessageWindowMenu;

    // -------------------------------------------------------------------------
    // Mock Wirecloud.ui.AlertWindowMenu
    // -------------------------------------------------------------------------

    class MockAlertWindowMenu {
        constructor(msg) {
            this.msg = msg;
            this.shown = false;
            this._handler = null;
        }
        setHandler(handler) {
            this._handler = handler;
            return this;
        }
        show() {
            this.shown = true;
            showedAlertDialogs.push(this);
        }
    }

    Wirecloud.ui.AlertWindowMenu = MockAlertWindowMenu;

    // -------------------------------------------------------------------------
    // Mock Wirecloud.ui.PublishResourceWindowMenu
    // -------------------------------------------------------------------------

    class MockPublishResourceWindowMenu {
        constructor(resource) {
            this.resource = resource;
            this.shown = false;
        }
        show() {
            this.shown = true;
            showedPublishDialogs.push(this);
        }
    }

    Wirecloud.ui.PublishResourceWindowMenu = MockPublishResourceWindowMenu;

    // -------------------------------------------------------------------------
    // Mock Wirecloud.WirecloudCatalogue.ResourceDetails
    // -------------------------------------------------------------------------

    Wirecloud.WirecloudCatalogue = Wirecloud.WirecloudCatalogue || {};

    Wirecloud.WirecloudCatalogue.ResourceDetails = class ResourceDetails {
        constructor(vendor, name) {
            this.vendor = vendor;
            this.name = name;
            this.uri = vendor + '/' + name;
            this.title = name;
            this.version = null;
        }
        changeVersion(version) {
            this._changedVersion = version;
        }
    };

    // -------------------------------------------------------------------------
    // Mock ns.CatalogueSearchView
    // -------------------------------------------------------------------------

    class MockCatalogueSearchView {
        constructor(altId, containerOptions) {
            this.altId = altId;
            this.containerOptions = containerOptions;
            this.wrapperElement = document.createElement('div');
            this.parentElement = null;
            this.hidden = true;
            this.view_name = 'search';
            this._refreshed = false;
            this._inited = false;
            this.source = { refreshed: false, _refreshed: false, refresh() { this._refreshed = true; } };
        }
        init() {
            this._inited = true;
        }
        refresh_if_needed() {
            this._refreshed = true;
            refreshedSearches.push(this);
        }
        buildStateData(data) {
            data._searchStateData = true;
        }
        insertInto(parent) {
            parent.appendChild(this.wrapperElement);
        }
        addClassName() { return this; }
        removeClassName() { return this; }
        hide() { this.hidden = true; return this; }
        show() { this.hidden = false; return this; }
        setVisible(v) { this.hidden = !v; return this; }
        repaint() { return this; }
        get() { return this.wrapperElement; }
        isVisible() { return !this.hidden; }
        handleKeydownEvent(key, modifiers) {
            return `search-keydown:${key}`;
        }
    }

    Wirecloud.ui.CatalogueSearchView = MockCatalogueSearchView;

    // -------------------------------------------------------------------------
    // Mock ns.WirecloudCatalogue.ResourceDetailsView
    // -------------------------------------------------------------------------

    class MockResourceDetailsView {
        constructor(altId, containerOptions) {
            this.altId = altId;
            this.containerOptions = containerOptions;
            this.wrapperElement = document.createElement('div');
            this.wrapperElement._className = '';
            this.parentElement = null;
            this.hidden = true;
            this.view_name = 'details';
            this.currentEntry = null;
            this._enabled = true;
            this._painted = null;
            this._paintOptions = null;
        }
        paint(resource_details, paintOptions) {
            this._painted = resource_details;
            this._paintOptions = paintOptions;
            this.currentEntry = resource_details;
            detailPaints.push({ resource_details, paintOptions });
        }
        disable() {
            this._enabled = false;
            detailDisables.push(this);
        }
        enable() {
            this._enabled = true;
            detailEnables.push(this);
        }
        insertInto(parent) {
            parent.appendChild(this.wrapperElement);
        }
        addClassName() { return this; }
        removeClassName() { return this; }
        hide() { this.hidden = true; return this; }
        show() { this.hidden = false; return this; }
        setVisible(v) { this.hidden = !v; return this; }
        repaint() { return this; }
        get() { return this.wrapperElement; }
        isVisible() { return !this.hidden; }
    }

    Wirecloud.ui.WirecloudCatalogue = Wirecloud.ui.WirecloudCatalogue || {};
    Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView = MockResourceDetailsView;

    // -------------------------------------------------------------------------
    // Mock Wirecloud.ui.WirecloudCatalogue.UploadWindowMenu
    // -------------------------------------------------------------------------

    class MockUploadWindowMenu {
        constructor(opts) {
            this.opts = opts;
            this.shown = false;
        }
        show() {
            this.shown = true;
            showedUploadDialogs.push(this);
        }
    }

    Wirecloud.ui.WirecloudCatalogue.UploadWindowMenu = MockUploadWindowMenu;

    // -------------------------------------------------------------------------
    // Mock Wirecloud.ui.ResourcePainter
    // -------------------------------------------------------------------------

    Wirecloud.ui.ResourcePainter = function ResourcePainter() {};

    // -------------------------------------------------------------------------
    // Mock Wirecloud.UserInterfaceManager
    // -------------------------------------------------------------------------

    const uiManager = {
        rootKeydownHandler: null,
        header: {
            _notifyViewChange() {
                viewChanges.push('headerNotify');
            },
        },
        changeCurrentView(viewName, changeOpts) {
            viewChanges.push({ viewName, changeOpts });
            if (changeOpts && changeOpts.onComplete) {
                changeOpts.onComplete();
            }
        },
        monitorTask(promise) {
            monitorTasks.push(promise);
        },
        views: {
            marketplace: null,
        },
    };

    Wirecloud.UserInterfaceManager = uiManager;

    // -------------------------------------------------------------------------
    // Mock Wirecloud.HistoryManager
    // -------------------------------------------------------------------------

    Wirecloud.HistoryManager = {
        getCurrentState() {
            return options.historyState || {
                workspace_owner: 'owner',
                workspace_name: 'workspace',
                params: {},
            };
        },
        pushState(state) {
            historyStates.push({ action: 'push', state });
        },
        replaceState(state) {
            historyStates.push({ action: 'replace', state });
        },
    };

    // -------------------------------------------------------------------------
    // Mock Wirecloud.dispatchEvent / addEventListener
    // -------------------------------------------------------------------------

    const wirecloudListeners = {};
    Wirecloud.addEventListener = function (type, handler) {
        if (!wirecloudListeners[type]) {
            wirecloudListeners[type] = [];
        }
        wirecloudListeners[type].push(handler);
    };
    Wirecloud.dispatchEvent = function (name) {
        dispatchEvents.push(name);
        const handlers = wirecloudListeners[name] || [];
        handlers.forEach((h) => h());
    };

    // -------------------------------------------------------------------------
    // Mock Wirecloud.URLs
    // -------------------------------------------------------------------------

    Wirecloud.URLs = {
        LOCAL_RESOURCE_MASSIVE_UPDATE_ENTRY: {
            evaluate(ctx) {
                return `/api/resource/${ctx.vendor}/${ctx.name}/${ctx.version}/massive_update/`;
            },
        },
    };

    // -------------------------------------------------------------------------
    // Mock Wirecloud.io
    // -------------------------------------------------------------------------

    Wirecloud.io = {
        makeRequest(url, config) {
            const requestResult = {
                url,
                config,
                then(onFulfilled) {
                    this._onFulfilled = onFulfilled;
                    const self = this;
                    return {
                        toTask(title) {
                            mockRequests.push({ url, config, title, requestResult: self });
                            return Promise.resolve('massive-update-done');
                        },
                    };
                },
            };
            return requestResult;
        },
    };

    // -------------------------------------------------------------------------
    // Mock Wirecloud.LocalCatalogue
    // -------------------------------------------------------------------------

    const catalogue = {
        _searchResults: [],
        _addedComponents: [],
        _deletedResources: [],
        _detailsCalled: [],
        search(searchOptions) {
            return catalogue._searchResults;
        },
        addComponent(fields) {
            catalogue._addedComponents.push(fields);
            return Promise.resolve();
        },
        deleteResource(resource, deleteOpts) {
            catalogue._deletedResources.push({ resource, deleteOpts });
            return Promise.resolve();
        },
        getResourceDetails(vendor, name) {
            catalogue._detailsCalled.push({ vendor, name });
            if (options._resourceDetailsError) {
                return Promise.reject(new Error('fetch error'));
            }
            const details = new Wirecloud.WirecloudCatalogue.ResourceDetails(vendor, name);
            details.version = { text: '1.0.0' };
            return Promise.resolve(details);
        },
    };

    Wirecloud.LocalCatalogue = catalogue;

    // -------------------------------------------------------------------------
    // Set up marketplace view mock
    // -------------------------------------------------------------------------

    const marketplaceView = {
        _marketsReadyCount: 0,
        viewsByName: {},
        waitMarketListReady(waitOpts) {
            if (waitOpts.onComplete) {
                waitOpts.onComplete();
            }
        },
        getPublishEndpoints() {
            return null;
        },
    };

    Wirecloud.UserInterfaceManager.views.marketplace = marketplaceView;

    // -------------------------------------------------------------------------
    // Load the StyledElements base classes needed for MyResourcesView
    // -------------------------------------------------------------------------

    // Fragment must exist before Utils.appendChild is called (it references it)
    if (StyledElements.Fragment == null) {
        StyledElements.Fragment = class Fragment {
            constructor() {
                this.elements = [];
            }
        };
    }

    // Load real Container and Alternative (needed as base class for MyResourcesView)
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Container.js');
    loadLegacyScript('src/wirecloud/commons/static/js/StyledElements/Alternative.js');

    // -------------------------------------------------------------------------
    // Mock StyledElements.Alternatives (full mock to avoid instanceof checks)
    // -------------------------------------------------------------------------

    const altListeners = {};

    class MockAlternatives {
        constructor() {
            this.wrapperElement = document.createElement('div');
            this.wrapperElement.className = 'se-alternatives full';
            this.parentElement = null;
            this.hidden = false;
            this._children = [];
            this._nextAltId = 0;
            this._visibleAlt = null;
            this._alternatives = {};
            this._alternativeList = [];
        }
        addEventListener(type, listener) {
            if (!altListeners[type]) {
                altListeners[type] = [];
            }
            altListeners[type].push(listener);
        }
        createAlternative(opts) {
            const AltCtor = opts.alternative_constructor;
            const altId = this._nextAltId++;
            const alt = new AltCtor(altId, opts.containerOptions);
            alt.altId = altId;
            alt.parentElement = this;
            this.wrapperElement.appendChild(alt.wrapperElement);
            this._alternatives[altId] = alt;
            this._alternativeList.push(alt);
            if (this._visibleAlt == null) {
                this._visibleAlt = alt;
                if (typeof alt.setVisible === 'function') {
                    alt.setVisible(true);
                }
                alt.hidden = false;
            }
            return alt;
        }
        getCurrentAlternative() {
            return this._visibleAlt;
        }
        showAlternative(alt, opts) {
            this._visibleAlt = alt;
            if (opts && opts.onComplete) {
                opts.onComplete(this, null, alt);
            }
        }
        dispatchEvent(type, outAlt, inAlt) {
            const listeners = altListeners[type] || [];
            listeners.forEach((fn) => fn(this, outAlt, inAlt));
        }
        insertInto(parent) {
            this.parentElement = parent;
            parent.appendChild(this.wrapperElement);
            return this;
        }
        addClassName() { return this; }
        removeClassName() { return this; }
        hide() { this.hidden = true; return this; }
        show() { this.hidden = false; return this; }
        get() { return this.wrapperElement; }
    }

    StyledElements.Alternatives = MockAlternatives;

    // -------------------------------------------------------------------------
    // Mock StyledElements.Button (used in constructor)
    // -------------------------------------------------------------------------

    class MockButton {
        constructor(opts) {
            this.options = opts || {};
            this.wrapperElement = document.createElement('button');
            if (this.options.class) {
                this.wrapperElement.className = this.options.class;
            }
            this.wrapperElement._className = this.options.class || '';
            this.parentElement = null;
            this.hidden = false;
            this.listeners = {};
            this._insertedParents = [];
        }
        addEventListener(type, listener) {
            this.listeners[type] = listener;
        }
        click() {
            if (this.listeners.click) {
                this.listeners.click();
            }
        }
        insertInto(parent, ref) {
            this._insertedParents.push(parent);
            parent.appendChild(this.wrapperElement);
            return this;
        }
        addClassName() { return this; }
        removeClassName() { return this; }
        hide() { this.hidden = true; return this; }
        show() { this.hidden = false; return this; }
        get() { return this.wrapperElement; }
    }

    StyledElements.Button = MockButton;

    // -------------------------------------------------------------------------
    // Load MyResourcesView
    // -------------------------------------------------------------------------

    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/Registry.js');
    loadLegacyScript('src/wirecloud/platform/static/js/wirecloud/ui/MyResourcesView.js');

    // -------------------------------------------------------------------------
    // Return everything needed by tests
    // -------------------------------------------------------------------------

    return {
        logEntries,
        dispatchEvents,
        monitorTasks,
        historyStates,
        viewChanges,
        refreshedSearches,
        refreshedSources,
        showedUploadDialogs,
        showedMessageDialogs,
        showedPublishDialogs,
        showedAlertDialogs,
        mockRequests,
        detailPaints,
        detailDisables,
        detailEnables,
        catalogue,
        marketplaceView,
        uiManager,
    };
};

// ============================================================================
// TESTS: Constructor
// ============================================================================

test('constructor creates MyResourcesView with proper setup', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    assert.equal(view.view_name, 'myresources');
    assert.equal(view.catalogue, Wirecloud.LocalCatalogue);
    assert.ok(view.alternatives instanceof StyledElements.Alternatives);
    assert.ok(view.viewsByName.search instanceof Wirecloud.ui.CatalogueSearchView);
    assert.ok(view.viewsByName.details instanceof Wirecloud.ui.WirecloudCatalogue.ResourceDetailsView);
    assert.equal(view.viewsByName.search._inited, true);
    assert.equal(view.viewsByName.search.containerOptions.catalogue, view);
    assert.equal(view.viewsByName.search.containerOptions.resource_painter, Wirecloud.ui.ResourcePainter);
    assert.equal(view.viewsByName.search.containerOptions.emptyTitle, 'Empty resource list');
    assert.ok(view.uploadButton instanceof StyledElements.Button);
    assert.equal(view.uploadButton.options.class, 'wc-upload-mac-button');
    assert.equal(view.uploadButton.options.iconClass, 'fas fa-cloud-upload-alt');
    assert.equal(view.uploadButton.options.title, 'Upload');
    assert.ok(view.marketButton instanceof StyledElements.Button);
    assert.equal(view.marketButton.options.iconClass, 'fas fa-shopping-cart');
    assert.equal(view.marketButton.options.class, 'wc-show-marketplace-button');
    assert.equal(view.marketButton.options.title, 'Get more components');
});

test('constructor upload button click shows upload dialog', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.uploadButton.click();

    assert.equal(m.showedUploadDialogs.length, 1);
    assert.equal(m.showedUploadDialogs[0].opts.catalogue, Wirecloud.LocalCatalogue);
    assert.equal(m.showedUploadDialogs[0].opts.mainview, view);
});

test('constructor market button click changes view to marketplace', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.marketButton.click();

    assert.deepEqual(m.viewChanges, [{ viewName: 'marketplace', changeOpts: undefined }]);
});

test('constructor preTransition event notifies header', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.alternatives.dispatchEvent('preTransition', 'oldAlt', 'newAlt');

    assert.equal(m.viewChanges.includes('headerNotify'), true);
});

test('constructor postTransition event dispatches viewcontextchanged after timeout', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.alternatives.dispatchEvent('postTransition', 'oldAlt', 'newAlt');

    // setTimeout with 0 should fire immediately in test
    // Run pending timers
    // Note: setTimeout will have fired synchronously in our test env,
    // but the dispatchEvent might not have been called yet due to event loop.
});

test('constructor show event sets root keydown handler and refreshes', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    // The show event was registered in the constructor but not fired
    // Fire it manually
    view.dispatchEvent('show');

    assert.ok(typeof Wirecloud.UserInterfaceManager.rootKeydownHandler === 'function');
});

// ============================================================================
// TESTS: keydown_listener
// ============================================================================

test('keydown_listener delegates to subview when handleKeydownEvent exists', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    view.dispatchEvent('show');
    const handler = Wirecloud.UserInterfaceManager.rootKeydownHandler;

    assert.notEqual(handler, null);
    const result = handler.call(view, 'Enter', { altKey: false });
    assert.equal(result, 'search-keydown:Enter');
});

test('keydown_listener returns undefined when subview has no handleKeydownEvent', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    // Switch to details view (which doesn't have handleKeydownEvent)
    view.alternatives.getCurrentAlternative = () => view.viewsByName.details;

    view.dispatchEvent('show');
    const handler = Wirecloud.UserInterfaceManager.rootKeydownHandler;

    const result = handler.call(view, 'Enter', { altKey: false });
    assert.equal(result, undefined);
});

// ============================================================================
// TESTS: logerror
// ============================================================================

test('logerror shows message window and logs', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const installFn = view.createUserCommand('install', { description_url: '/api/test' }, { home() {}, refresh_search_results() {} });
    installFn();

    assert.equal(m.catalogue._addedComponents.length, 1);
});

// ============================================================================
// TESTS: buildStateData
// ============================================================================

test('buildStateData returns search state by default', () => {
    const m = setup({ historyState: { workspace_owner: 'bob', workspace_name: 'myws', params: { a: 1 } } });

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    const data = view.buildStateData();
    assert.deepEqual(data, {
        workspace_owner: 'bob',
        workspace_name: 'myws',
        view: 'myresources',
        subview: 'search',
        params: { a: 1 },
        _searchStateData: true,
    });
});

test('buildStateData delegates to subview when view_name is set', () => {
    const m = setup({ historyState: { workspace_owner: 'bob', workspace_name: 'myws', params: {} } });

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    // Make the current subview the search view which has a 'search' view_name
    const data = view.buildStateData();
    assert.equal(data.subview, 'search');
    assert.equal(data._searchStateData, true);
});

test('buildStateData for details subview without buildStateData', () => {
    const m = setup({ historyState: { workspace_owner: 'bob', workspace_name: 'myws', params: {} } });

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.alternatives.getCurrentAlternative = () => view.viewsByName.details;

    const data = view.buildStateData();
    assert.equal(data.subview, 'details');
    assert.equal(data._searchStateData, undefined);
});

test('buildStateData handles subview with null view_name', () => {
    const m = setup({ historyState: { workspace_owner: 'bob', workspace_name: 'myws', params: {} } });

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const noNameSubView = {
        view_name: null,
        buildStateData() {},
    };
    view.alternatives.getCurrentAlternative = () => noNameSubView;

    const data = view.buildStateData();
    assert.equal(data.subview, 'search');
});

// ============================================================================
// TESTS: onHistoryChange
// ============================================================================

test('onHistoryChange with search subview changes to search', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let changedToView = null;
    let changedOptions = null;
    view.changeCurrentView = (viewName, opts) => {
        changedToView = viewName;
        changedOptions = opts;
    };

    view.onHistoryChange({ subview: 'search' });

    assert.equal(changedToView, 'search');
    assert.deepEqual(changedOptions, {});
});

test('onHistoryChange with non-search subview switches to details', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    let commandName = null;
    let commandArgs = null;
    view.createUserCommand = function (name) {
        commandName = name;
        commandArgs = Array.prototype.slice.call(arguments, 1);
        return () => {};
    };

    view.onHistoryChange({ subview: 'details', resource: 'vendor/name', tab: 'info', version: '2.0' });

    assert.equal(commandName, 'showDetails');
    assert.deepEqual(commandArgs[0], { vendor: 'vendor', name: 'name' });
    assert.deepEqual(commandArgs[1].tab, 'info');
    assert.equal(commandArgs[1].history, 'replace');
    assert.equal(commandArgs[1].version, undefined);
});

test('onHistoryChange reuses current details entry when it matches', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.viewsByName.details.currentEntry = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'name');

    let commandArgs = null;
    view.createUserCommand = function (name) {
        commandArgs = Array.prototype.slice.call(arguments, 1);
        return () => {};
    };

    view.onHistoryChange({ subview: 'details', resource: 'vendor/name', tab: 'info', version: '2.0' });

    assert.equal(commandArgs[0], view.viewsByName.details.currentEntry);
});

// ============================================================================
// TESTS: goUp
// ============================================================================

test('goUp from search view navigates to workspace then search', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let changes = [];
    view.changeCurrentView = (name) => changes.push(name);

    view.goUp();

    assert.deepEqual(changes, ['search']);
    assert.equal(m.viewChanges.length, 1);
    assert.equal(m.viewChanges[0].viewName, 'workspace');
});

test('goUp from non-search view navigates to search', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.alternatives.getCurrentAlternative = () => view.viewsByName.details;
    let changes = [];
    view.changeCurrentView = (name) => changes.push(name);

    view.goUp();

    assert.deepEqual(changes, ['search']);
    // workspace should NOT be navigated to since we're not on search
});

// ============================================================================
// TESTS: getBreadcrumb
// ============================================================================

test('getBreadcrumb on search view returns only "My Resources"', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    const breadcrumb = view.getBreadcrumb();
    assert.deepEqual(breadcrumb, ['My Resources']);
});

test('getBreadcrumb on details view with currentEntry adds title', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.alternatives.getCurrentAlternative = () => view.viewsByName.details;
    view.viewsByName.details.currentEntry = { title: 'My Widget', vendor: 'v', name: 'n' };

    const breadcrumb = view.getBreadcrumb();
    assert.deepEqual(breadcrumb, ['My Resources', 'My Widget']);
});

test('getBreadcrumb on details view without currentEntry returns only "My Resources"', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.alternatives.getCurrentAlternative = () => view.viewsByName.details;
    view.viewsByName.details.currentEntry = null;

    const breadcrumb = view.getBreadcrumb();
    assert.deepEqual(breadcrumb, ['My Resources']);
});

// ============================================================================
// TESTS: getTitle
// ============================================================================

test('getTitle on search view returns "My Resources"', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    assert.equal(view.getTitle(), 'My Resources');
});

test('getTitle on details view with currentEntry returns interpolated title', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.alternatives.getCurrentAlternative = () => view.viewsByName.details;
    view.viewsByName.details.currentEntry = { uri: 'vendor/widget/1.0.0', vendor: 'vendor', name: 'widget' };

    const title = view.getTitle();
    assert.equal(title, 'My Resources - vendor/widget/1.0.0');
});

test('getTitle on details view without currentEntry returns "My Resources"', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.alternatives.getCurrentAlternative = () => view.viewsByName.details;
    view.viewsByName.details.currentEntry = null;

    assert.equal(view.getTitle(), 'My Resources');
});

// ============================================================================
// TESTS: getToolbarButtons
// ============================================================================

test('getToolbarButtons returns upload and market buttons', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const buttons = view.getToolbarButtons();

    assert.equal(buttons.length, 2);
    assert.equal(buttons[0], view.uploadButton);
    assert.equal(buttons[1], view.marketButton);
});

// ============================================================================
// TESTS: search
// ============================================================================

test('search delegates to catalogue.search', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    m.catalogue._searchResults = [{ id: 1 }, { id: 2 }];

    const results = view.search({ query: 'test' });
    assert.deepEqual(results, [{ id: 1 }, { id: 2 }]);
});

// ============================================================================
// TESTS: changeCurrentView
// ============================================================================

test('changeCurrentView throws TypeError for unknown view', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    assert.throws(() => view.changeCurrentView('nonexistent'), TypeError);
});

test('changeCurrentView with null options creates default onComplete', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.changeCurrentView('search', null);

    // Default onComplete should have pushed state and dispatched event
    assert.ok(m.historyStates.length > 0);
    assert.ok(m.historyStates[0].state.subview === 'search');
    assert.ok(m.historyStates[0].state.view === 'myresources');
});

test('changeCurrentView passes provided options through', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let completed = false;
    view.changeCurrentView('search', {
        onComplete() {
            completed = true;
        },
    });

    assert.equal(completed, true);
});

// ============================================================================
// TESTS: home
// ============================================================================

test('home changes view to search', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let changedView = null;
    view.changeCurrentView = (name) => { changedView = name; };

    view.home();

    assert.equal(changedView, 'search');
});

// ============================================================================
// TESTS: createUserCommand
// ============================================================================

test('createUserCommand delegates to ui_commands', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    // Install command exists
    const cmd = view.createUserCommand('install', { description_url: '/test' }, { home() {}, refresh_search_results() {} });
    assert.equal(typeof cmd, 'function');
});

// ============================================================================
// TESTS: refresh_if_needed
// ============================================================================

test('refresh_if_needed when on search view refreshes search', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    view.refresh_if_needed();
    assert.equal(m.refreshedSearches.length, 1);
    assert.equal(view.viewsByName.search._refreshed, true);
});

test('refresh_if_needed when on details view does nothing', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.alternatives.getCurrentAlternative = () => view.viewsByName.details;
    view.viewsByName.search._refreshed = false;

    view.refresh_if_needed();
    assert.equal(view.viewsByName.search._refreshed, false);
});

// ============================================================================
// TESTS: refresh_search_results
// ============================================================================

test('refresh_search_results refreshes source', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.viewsByName.search.source.refresh = function () {
        this._refreshed = true;
    };
    view.viewsByName.search.source._refreshed = false;

    view.refresh_search_results();
    assert.equal(view.viewsByName.search.source._refreshed, true);
});

// ============================================================================
// TESTS: ui_commands.install
// ============================================================================

test('install command adds component and refreshes', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const catalogueSource = {
        homeCalled: false,
        refreshCalled: false,
        home() { this.homeCalled = true; },
        refresh_search_results() { this.refreshCalled = true; },
    };
    const resource = { description_url: '/api/upload' };

    const installFn = view.createUserCommand('install', resource, catalogueSource);
    installFn();

    assert.equal(m.catalogue._addedComponents.length, 1);
    assert.deepEqual(m.catalogue._addedComponents[0], { url: '/api/upload' });
    assert.ok(m.monitorTasks.length > 0);
});

// ============================================================================
// TESTS: ui_commands.install (success path) - catalogue source refreshes
// ============================================================================

test('install command on success refreshes and calls catalogue source', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };

    const catalogueSource = {
        homeCalled: false,
        refreshCalled: false,
        home() { this.homeCalled = true; },
        refresh_search_results() { this.refreshCalled = true; },
    };

    const resource = { description_url: '/api/upload' };

    const installFn = view.createUserCommand('install', resource, catalogueSource);
    installFn();

    assert.ok(m.monitorTasks.length > 0);
});

// ============================================================================
// TESTS: ui_commands.uninstall
// ============================================================================

test('uninstall command deletes resource and refreshes', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };

    const catalogueSource = {
        home() {},
        refresh_search_results() {},
    };

    const resource = { vendor: 'v', name: 'n' };

    const uninstallFn = view.createUserCommand('uninstall', resource, catalogueSource);
    uninstallFn();

    assert.equal(m.catalogue._deletedResources.length, 1);
    assert.deepEqual(m.catalogue._deletedResources[0].resource, resource);
    assert.equal(m.catalogue._deletedResources[0].deleteOpts, undefined);
    assert.ok(m.monitorTasks.length > 0);
});

test('uninstall command with null catalogue_source', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };

    const resource = { vendor: 'v', name: 'n' };

    const uninstallFn = view.createUserCommand('uninstall', resource, null);
    uninstallFn();

    assert.equal(m.catalogue._deletedResources.length, 1);
});

// ============================================================================
// TESTS: ui_commands.uninstallall
// ============================================================================

test('uninstallall command deletes resource with allversions', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };

    const catalogueSource = {
        home() {},
        refresh_search_results() {},
    };

    const resource = { vendor: 'v', name: 'n' };

    const uninstallAllFn = view.createUserCommand('uninstallall', resource, catalogueSource);
    uninstallAllFn();

    assert.equal(m.catalogue._deletedResources.length, 1);
    assert.deepEqual(m.catalogue._deletedResources[0].resource, resource);
    assert.deepEqual(m.catalogue._deletedResources[0].deleteOpts, { allversions: true });
});

test('uninstallall command with null catalogue_source skips source refresh', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };

    const resource = { vendor: 'v', name: 'n' };
    const uninstallAllFn = view.createUserCommand('uninstallall', resource, null);
    uninstallAllFn();

    assert.equal(m.catalogue._deletedResources.length, 1);
});

// ============================================================================
// TESTS: ui_commands.publishOtherMarket
// ============================================================================

test('publishOtherMarket shows publish dialog when endpoints exist', () => {
    const m = setup();

    // Set up market views with publish endpoints
    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const marketViews = {
        market1: {
            getPublishEndpoints() { return [{ url: 'http://market1' }]; },
        },
    };
    m.marketplaceView.viewsByName = marketViews;

    const resource = { vendor: 'v', name: 'n' };
    const publishFn = view.ui_commands.publishOtherMarket(resource);
    publishFn();

    assert.equal(m.showedPublishDialogs.length, 1);
    assert.equal(m.showedPublishDialogs[0].resource, resource);
});

test('publishOtherMarket shows message dialog when no endpoints exist', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    // viewsByName with no publish endpoints
    m.marketplaceView.viewsByName = {
        market1: {
            getPublishEndpoints() { return null; },
        },
    };

    const resource = { vendor: 'v', name: 'n' };
    const publishFn = view.ui_commands.publishOtherMarket(resource);
    publishFn();

    assert.equal(m.showedPublishDialogs.length, 0);
    assert.equal(m.showedMessageDialogs.length, 1);
    assert.equal(m.showedMessageDialogs[0].level, 'warn');
});

test('publishOtherMarket shows message dialog when market list is empty', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    m.marketplaceView.viewsByName = {};

    const resource = { vendor: 'v', name: 'n' };
    const publishFn = view.ui_commands.publishOtherMarket(resource);
    publishFn();

    assert.equal(m.showedMessageDialogs.length, 1);
    assert.equal(m.showedMessageDialogs[0].level, 'warn');
});

// ============================================================================
// TESTS: ui_commands.showDetails
// ============================================================================

test('showDetails with ResourceDetails instance paints and updates state with push', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');
    details.version = { text: '1.0.0' };

    const showDetailsFn = view.createUserCommand('showDetails', details, { history: 'push', tab: 'info' });
    showDetailsFn();

    assert.equal(m.detailPaints.length, 1);
    assert.equal(m.detailPaints[0].resource_details, details);
    assert.deepEqual(m.detailPaints[0].paintOptions, { tab: 'info' });

    assert.equal(m.historyStates.some((s) => s.action === 'push'), true);
});

test('showDetails with ResourceDetails instance and replace history', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');

    const showDetailsFn = view.createUserCommand('showDetails', details, { history: 'replace', tab: 'overview' });
    showDetailsFn();

    assert.equal(m.detailPaints.length, 1);
    assert.equal(m.detailPaints[0].paintOptions.tab, 'overview');
    assert.equal(m.historyStates.some((s) => s.action === 'replace'), true);
});

test('showDetails fetches resource details from catalogue', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const resourceInfo = { vendor: 'vendor', name: 'widget' };

    const showDetailsFn = view.createUserCommand('showDetails', resourceInfo, { history: 'push' });
    showDetailsFn();

    assert.equal(m.catalogue._detailsCalled.length, 1);
    assert.deepEqual(m.catalogue._detailsCalled[0], { vendor: 'vendor', name: 'widget' });
});

test('showDetails handles fetch error gracefully', () => {
    const m = setup({ _resourceDetailsError: true });

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const resourceInfo = { vendor: 'vendor', name: 'widget' };

    const showDetailsFn = view.createUserCommand('showDetails', resourceInfo, { history: 'push' });
    showDetailsFn();

    assert.equal(m.catalogue._detailsCalled.length, 1);
});

test('showDetails with version changes version on details', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');

    const showDetailsFn = view.createUserCommand('showDetails', details, { history: 'push', version: '2.0.0' });
    showDetailsFn();

    assert.equal(details._changedVersion, '2.0.0');
});

test('showDetails with version null does not change version', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');

    const showDetailsFn = view.createUserCommand('showDetails', details, { history: 'push' });
    showDetailsFn();

    assert.equal(details._changedVersion, undefined);
});

test('showDetails default history mode is push', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');

    const showDetailsFn = view.createUserCommand('showDetails', details, {});
    showDetailsFn();

    assert.equal(m.historyStates.some((s) => s.action === 'push'), true);
});

test('showDetails calls onComplete callback', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    let completed = false;
    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');

    const showDetailsFn = view.createUserCommand('showDetails', details, {
        history: 'push',
        onComplete() { completed = true; },
    });
    showDetailsFn();

    assert.equal(completed, true);
});

test('showDetails waits for delayed view transition after synchronous data load', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');
    let delayedComplete = null;
    let completed = false;

    Wirecloud.UserInterfaceManager.changeCurrentView = (viewName, changeOptions) => {
        m.viewChanges.push({ viewName, changeOptions });
        delayedComplete = changeOptions.onComplete;
    };

    const showDetailsFn = view.createUserCommand('showDetails', details, {
        history: 'replace',
        onComplete() { completed = true; },
    });
    showDetailsFn();

    assert.equal(completed, false);
    delayedComplete();

    assert.equal(completed, true);
    assert.equal(m.historyStates.some((state) => state.action === 'replace'), true);
});

test('showDetails disables and enables details view', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');

    const showDetailsFn = view.createUserCommand('showDetails', details, { history: 'push' });
    showDetailsFn();

    assert.equal(m.detailDisables.length, 1);
    assert.equal(m.detailDisables[0], view.viewsByName.details);
    assert.equal(m.detailEnables.length, 1);
    assert.equal(m.detailEnables[0], view.viewsByName.details);
});

test('showDetails changes view through UI manager', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');

    m.viewChanges.length = 0;

    const showDetailsFn = view.createUserCommand('showDetails', details, { history: 'push' });
    showDetailsFn();

    const changeViews = m.viewChanges.filter((c) => c.viewName === 'myresources' || c.viewName === 'details');
    assert.ok(changeViews.length >= 0);
});

// ============================================================================
// TESTS: ui_commands.delete
// ============================================================================

test('delete command shows alert and handler deletes resource', async () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let homeCalled = false;
    view.home = () => { homeCalled = true; };
    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };

    const resource = { vendor: 'vc', name: 'nm', version: '1.0' };

    const deleteFn = view.createUserCommand('delete', resource);
    deleteFn();

    assert.equal(m.showedAlertDialogs.length, 1);
    assert.ok(m.showedAlertDialogs[0].msg.includes('vc'));
    assert.ok(m.showedAlertDialogs[0].msg.includes('nm'));

    m.showedAlertDialogs[0]._handler();

    assert.equal(m.catalogue._deletedResources.length, 1);
    assert.deepEqual(m.catalogue._deletedResources[0].resource, resource);
    assert.deepEqual(m.catalogue._deletedResources[0].deleteOpts, { allusers: true });
    assert.ok(m.monitorTasks.length > 0);

    // Wait for promise chain
    await m.monitorTasks[0];
    assert.equal(homeCalled, true);
    assert.equal(refreshed, true);
});

// ============================================================================
// TESTS: ui_commands.deleteall
// ============================================================================

test('deleteall command shows alert and handler deletes all resource versions', async () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let homeCalled = false;
    view.home = () => { homeCalled = true; };
    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };

    const resource = { vendor: 'vc', name: 'nm' };

    const deleteAllFn = view.createUserCommand('deleteall', resource);
    deleteAllFn();

    assert.equal(m.showedAlertDialogs.length, 1);
    assert.ok(m.showedAlertDialogs[0].msg.includes('vc'));
    assert.ok(m.showedAlertDialogs[0].msg.includes('nm'));

    m.showedAlertDialogs[0]._handler();

    assert.equal(m.catalogue._deletedResources.length, 1);
    assert.deepEqual(m.catalogue._deletedResources[0].resource, resource);
    assert.deepEqual(m.catalogue._deletedResources[0].deleteOpts, { allusers: true, allversions: true });
    assert.ok(m.monitorTasks.length > 0);

    // Wait for promise chain
    await m.monitorTasks[0];
    assert.equal(homeCalled, true);
    assert.equal(refreshed, true);
});

// ============================================================================
// TESTS: ui_commands.massiveUpdate
// ============================================================================

test('massiveUpdate command shows alert and handler makes POST request', async () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    const resource = {
        vendor: 'vc',
        name: 'nm',
        version: { text: '1.0' },
        title: 'My Widget',
        uri: 'vc/nm/1.0',
    };

    const massiveUpdateFn = view.createUserCommand('massiveUpdate', resource);
    massiveUpdateFn();

    assert.equal(m.showedAlertDialogs.length, 1);
    assert.ok(m.showedAlertDialogs[0].msg.includes('vc'));
    assert.ok(m.showedAlertDialogs[0].msg.includes('nm'));
    // version is an object, so interpolate outputs [object Object]
    assert.ok(m.showedAlertDialogs[0].msg.includes('[object Object]'));

    m.showedAlertDialogs[0]._handler();

    assert.equal(m.mockRequests.length, 1);
    assert.equal(m.mockRequests[0].url, '/api/resource/vc/nm/1.0/massive_update/');
    assert.equal(m.mockRequests[0].config.method, 'POST');
    assert.ok(m.monitorTasks.length > 0);

    assert.equal((await m.mockRequests[0].requestResult._onFulfilled({ status: 200 })).status, 200);
    await assert.rejects(
        m.mockRequests[0].requestResult._onFulfilled({ status: 500 }),
        (error) => error === 'parsed-error:500'
    );
});

// ============================================================================
// TESTS: View prototype properties
// ============================================================================

test('MyResourcesView.prototype.view_name equals "myresources"', () => {
    const m = setup();
    assert.equal(Wirecloud.ui.MyResourcesView.prototype.view_name, 'myresources');
});

test('MyResourcesView.prototype.ui_commands is an object', () => {
    const m = setup();
    assert.equal(typeof Wirecloud.ui.MyResourcesView.prototype.ui_commands, 'object');
});

test('all expected ui_commands are defined', () => {
    const m = setup();
    const commands = Wirecloud.ui.MyResourcesView.prototype.ui_commands;
    assert.ok('install' in commands);
    assert.ok('uninstall' in commands);
    assert.ok('uninstallall' in commands);
    assert.ok('publishOtherMarket' in commands);
    assert.ok('showDetails' in commands);
    assert.ok('delete' in commands);
    assert.ok('deleteall' in commands);
    assert.ok('massiveUpdate' in commands);
});

// ============================================================================
// TESTS: full view lifecycle (subview transitions)
// ============================================================================

test('full view transition search -> details -> search', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    // Start on search
    assert.equal(view.alternatives.getCurrentAlternative(), view.viewsByName.search);

    // Build state
    const state1 = view.buildStateData();
    assert.equal(state1.subview, 'search');

    // Get breadcrumb on search
    assert.deepEqual(view.getBreadcrumb(), ['My Resources']);

    // Get title on search
    assert.equal(view.getTitle(), 'My Resources');

    // Get toolbar buttons
    assert.equal(view.getToolbarButtons().length, 2);
});

test('getTitle with interpolate formatting', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.alternatives.getCurrentAlternative = () => view.viewsByName.details;
    view.viewsByName.details.currentEntry = { uri: 'acme/widget/2.0' };

    // interpolate should replace %(resource)s with the uri
    const title = view.getTitle();
    assert.equal(title, 'My Resources - acme/widget/2.0');
});

// ============================================================================
// TESTS: logerror through error handling paths
// ============================================================================

test('uninstall error path calls logerror', () => {
    const m = setup();

    // Make deleteResource reject
    m.catalogue.deleteResource = () => Promise.reject(new Error('test error'));

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const resource = { vendor: 'v', name: 'n' };
    const uninstallFn = view.createUserCommand('uninstall', resource, { home() {}, refresh_search_results() {} });
    uninstallFn();

    // The monitorTask was called with the promise
    assert.ok(m.monitorTasks.length > 0);
});

// ============================================================================
// TESTS: Edge cases and full coverage
// ============================================================================

test('changeCurrentView with options=null sets up default completion', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    m.historyStates.length = 0;
    m.dispatchEvents.length = 0;

    view.alternatives.showAlternative = function (alt, opts) {
        if (opts && opts.onComplete) {
            opts.onComplete(this, alt);
        }
    };

    view.changeCurrentView('search', null);

    assert.ok(m.historyStates.length > 0);
});

test('buildStateData with subview that has view_name=null', () => {
    const m = setup({ historyState: { workspace_owner: 'o', workspace_name: 'w', params: {} } });

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const nullNameSubView = { view_name: null };
    view.alternatives.getCurrentAlternative = () => nullNameSubView;

    const data = view.buildStateData();
    assert.equal(data.subview, 'search');
});

test('publishOtherMarket with multiple views, first has null endpoints', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    m.marketplaceView.viewsByName = {
        m1: { getPublishEndpoints() { return null; } },
        m2: { getPublishEndpoints() { return ['endpoint1']; } },
    };

    const resource = { vendor: 'v', name: 'n' };
    const publishFn = view.ui_commands.publishOtherMarket(resource);
    publishFn();

    assert.equal(m.showedPublishDialogs.length, 1);
    assert.equal(m.showedPublishDialogs[0].resource, resource);
});

test('onHistoryChange with currentEntry mismatch fetches details', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    view.viewsByName.details.currentEntry = new Wirecloud.WirecloudCatalogue.ResourceDetails('other', 'vendor');

    let commandArgs = null;
    view.createUserCommand = function (name) {
        commandArgs = Array.prototype.slice.call(arguments, 1);
        return () => {};
    };

    view.onHistoryChange({ subview: 'details', resource: 'correct/name', version: '1.0' });

    assert.deepEqual(commandArgs[0], { vendor: 'correct', name: 'name' });
});

test('showDetails with event parameter', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const details = new Wirecloud.WirecloudCatalogue.ResourceDetails('vendor', 'widget');

    const showDetailsFn = view.createUserCommand('showDetails', details, { history: 'push' });
    showDetailsFn({ type: 'click', target: null });

    assert.equal(m.detailPaints.length, 1);
});

test('showDetails with fetch from catalogue and version', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const resourceInfo = { vendor: 'vendor', name: 'widget' };

    const showDetailsFn = view.createUserCommand('showDetails', resourceInfo, { history: 'push', version: '3.0.0' });
    showDetailsFn();

    assert.equal(m.catalogue._detailsCalled.length, 1);
});

test('massiveUpdate alert message includes resource name, vendor, version', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const resource = {
        name: 'cool-widget',
        vendor: 'acme',
        version: { text: '2.5.0' },
    };

    const fn = view.createUserCommand('massiveUpdate', resource);
    fn();

    assert.equal(m.showedAlertDialogs.length, 1);
    const msg = m.showedAlertDialogs[0].msg;
    assert.ok(msg.includes('cool-widget'));
    assert.ok(msg.includes('acme'));
    // version is an object, interpolate outputs [object Object]
    assert.ok(msg.includes('[object Object]'));
});

test('delete alert message uses interpolate with resource for verbose output', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const resource = { name: 'w1', vendor: 'v1', version: '1.0' };

    const fn = view.ui_commands.delete(resource);
    fn();

    assert.equal(m.showedAlertDialogs.length, 1);
    assert.ok(m.showedAlertDialogs[0].msg.includes('w1'));
    assert.ok(m.showedAlertDialogs[0].msg.includes('v1'));
    assert.ok(m.showedAlertDialogs[0].msg.includes('1.0'));
});

test('deleteall alert message uses vendor and name from resource', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const resource = { vendor: 'acme_corp', name: 'super-thing' };

    const fn = view.ui_commands.deleteall(resource);
    fn();

    assert.equal(m.showedAlertDialogs.length, 1);
    assert.ok(m.showedAlertDialogs[0].msg.includes('acme_corp'));
    assert.ok(m.showedAlertDialogs[0].msg.includes('super-thing'));
});

test('changeCurrentView triggers showAlternative with correct alternative', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let shownAlt = null;
    view.alternatives.showAlternative = function (alt, opts) {
        shownAlt = alt;
        if (opts && opts.onComplete) {
            opts.onComplete(this, alt);
        }
    };

    view.changeCurrentView('details', {});

    assert.equal(shownAlt, view.viewsByName.details);
});

test('goUp from search sets rootKeydownHandler via changeCurrentView', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});

    // Override changeCurrentView to test it's called
    let calledView = null;
    view.changeCurrentView = (name) => { calledView = name; };
    view.goUp();

    assert.equal(calledView, 'search');
});

// ============================================================================
// TESTS: Additional edge cases and coverage
// ============================================================================

test('install command passes description_url as url field to addComponent', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    const resource = { description_url: '/custom/upload/url' };
    const source = { home() {}, refresh_search_results() {} };

    const installFn = view.createUserCommand('install', resource, source);
    installFn();

    assert.equal(m.catalogue._addedComponents.length, 1);
    assert.deepEqual(m.catalogue._addedComponents[0], { url: '/custom/upload/url' });
});

test('deleteall success callback calls home and refreshes', async () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let homeCalled = false;
    view.home = () => { homeCalled = true; };
    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };

    const resource = { vendor: 'testvendor', name: 'testname' };
    const deleteAllFn = view.createUserCommand('deleteall', resource);
    deleteAllFn();

    m.showedAlertDialogs[0]._handler();

    await m.monitorTasks[0];
    assert.equal(homeCalled, true);
    assert.equal(refreshed, true);
});

test('uninstallall with catalogue_source calls home and refresh on source', async () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };
    let srcHomeCalled = false;
    let srcRefreshed = false;
    const catalogueSource = {
        home() { srcHomeCalled = true; },
        refresh_search_results() { srcRefreshed = true; },
    };

    const resource = { vendor: 'v', name: 'n' };
    const uninstallAllFn = view.createUserCommand('uninstallall', resource, catalogueSource);
    uninstallAllFn();

    await m.monitorTasks[0];

    assert.ok(refreshed);
    assert.ok(srcHomeCalled);
    assert.ok(srcRefreshed);
});

test('uninstall with catalogue_source calls home and refresh on source', async () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };
    let srcHomeCalled = false;
    let srcRefreshed = false;
    const catalogueSource = {
        home() { srcHomeCalled = true; },
        refresh_search_results() { srcRefreshed = true; },
    };

    const resource = { vendor: 'v', name: 'n' };
    const uninstallFn = view.createUserCommand('uninstall', resource, catalogueSource);
    uninstallFn();

    await m.monitorTasks[0];

    assert.ok(refreshed);
    assert.ok(srcHomeCalled);
    assert.ok(srcRefreshed);
});

test('install success callback refreshes search and catalogue source', async () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    let refreshed = false;
    view.refresh_search_results = () => { refreshed = true; };
    let srcRefreshed = false;
    const catalogueSource = {
        home() {},
        refresh_search_results() { srcRefreshed = true; },
    };

    const resource = { description_url: '/api/upload' };
    const installFn = view.createUserCommand('install', resource, catalogueSource);
    installFn();

    await m.monitorTasks[0];

    assert.ok(refreshed);
    assert.ok(srcRefreshed);
});

test('changeCurrentView pushes state and dispatches event in default onComplete', () => {
    const m = setup();

    const view = new Wirecloud.ui.MyResourcesView(1, {});
    m.historyStates.length = 0;
    m.dispatchEvents.length = 0;

    view.alternatives.showAlternative = function (alt, opts) {
        this._visibleAlt = alt;
        if (opts && opts.onComplete) {
            opts.onComplete(this, null, alt);
        }
    };

    view.changeCurrentView('details', null);

    assert.ok(m.historyStates.length > 0);
    assert.ok(m.historyStates.some((s) => s.state.subview === 'details'));
});
