// -*- coding: utf-8 -*-
// Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

// This file is part of Wirecloud.

// Wirecloud is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// Wirecloud is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.

// You should have received a copy of the GNU Affero General Public License
// along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.

import * as path from 'path';
import * as fs from 'fs';

// Load webpack settings JSON from an explicit path. We avoid importing a file from the project
// root to keep the repo root clean. The generator script writes to the system temp dir by default
// or to the path set in the WEBPACK_SETTINGS_JSON env var.
const defaultTempFile = path.join((process.env.TEMP || process.env.TMPDIR || '/tmp'), 'wirecloud_settings_js.json');
const settingsPath = process.env.WEBPACK_SETTINGS_JSON || process.env.npm_config_webpack_settings_json || defaultTempFile;

let settings: any = { installedApps: [] };
if (fs.existsSync(settingsPath)) {
    try {
        const raw = fs.readFileSync(settingsPath, 'utf-8');
        settings = JSON.parse(raw);
        console.log('Loaded settings JSON from', settingsPath);
    } catch (err) {
        console.warn('Could not parse settings JSON at', settingsPath, err);
    }
} else {
    console.warn('Settings JSON not found at', settingsPath, '- expected generated file with installedApps.');
}

const VIEWS: { [key: string]: string } = {
    'classic': 'platform',
    'smartphone': 'platform',
    'embedded': 'platform',
    'widget': 'widget',
    'index': 'platform'
};

const JS_VIEWS: string[] = ['classic', 'smartphone', 'embedded', 'widget', 'operator', 'bootstrap', 'oauth2'];

interface Theme {
    parent: string | null;
    get_css: (view: string) => string[];
    get_scripts: (view: string) => string[];
    path: string;
}

interface Plugin {
    get_scripts: (view: string) => string[];
    scripts_location: string | null;
    path: string;
}

const themePath = path.resolve(__dirname, '../themes');
const pluginPath = path.resolve(__dirname, '../');

const themes: { [key: string]: Theme } = {};
const plugins: { [key: string]: Plugin } = {};

// Search for theme directories in the themes directory. A theme is valid if it contains a theme.js file.
fs.readdirSync(themePath).forEach((theme) => {
    const themeDir = path.resolve(themePath, theme.replace(".", "/"));
    const themeFile = path.resolve(themeDir, 'theme.ts');

    if (fs.existsSync(themeFile)) {
        // Import the theme file
        themes[theme] = require(themeFile).default;
        themes[theme].path = themeDir;
    }
});

// Search for plugin directories in the wirecloud directory. A plugin is valid if it contains a plugin.js file.
// `settings.installedApps` can be either a list of strings (legacy) or a list of objects {name,module,path}.
const installedApps = Array.isArray(settings.installedApps) ? settings.installedApps : [];

installedApps.forEach((entry: any, i: number) => {
    let pluginName: string;
    let pluginDir: string | null = null;

    if (typeof entry === 'string') {
        pluginName = entry;
    } else if (entry && typeof entry === 'object') {
        pluginName = entry.name || entry.module || String(i);
        // If generator resolved a filesystem path, use it.
        if (entry.path) {
            pluginDir = entry.path;
        }
    } else {
        pluginName = String(i);
    }

    const pluginKey = `${String(i).padStart(5, '0')}_${pluginName}`;

    // If we don't have an explicit path, fall back to searching inside the repo's wirecloud folder
    if (!pluginDir) {
        pluginDir = path.resolve(pluginPath, pluginName);
    }

    const pluginFile = path.resolve(pluginDir, 'plugin.ts');

    if (fs.existsSync(pluginFile)) {
        try {
            plugins[pluginKey] = require(pluginFile).default;
            plugins[pluginKey].path = pluginDir;
        } catch (err) {
            console.warn('Error requiring plugin file', pluginFile, err);
        }
    }
});

const resolveCSSIncludePaths = (theme: string): string[] => {
    const includePaths = [];
    let currentTheme: string | null = theme;

    while (currentTheme) {
        const resultingPath = path.resolve(__dirname, `${themes[currentTheme].path}/static/css`);
        if (fs.existsSync(resultingPath)) {
            includePaths.push(resultingPath);
        }

        currentTheme = themes[currentTheme].parent;
    }

    return includePaths;
};

const createCSSEntries = (): { [key: string]: any } => {
    const entries: { [key: string]: any } = {};

    Object.keys(themes).forEach((theme) => {
        Object.keys(VIEWS).forEach((view) => {
            const entryKey = `${theme}_${view}_${VIEWS[view]}`;

            const css_files = new Set<string>();
            let currentTheme: string | null = theme;

            while (currentTheme) {
                themes[currentTheme].get_css(view).forEach((file) => {
                    css_files.add(file);
                });

                currentTheme = themes[currentTheme].parent;
            }

            const files = Array.from(css_files).map((file) => {
                let currentTheme: string | null = theme;

                let absolutePath = "";
                while (!fs.existsSync(absolutePath) && currentTheme) {
                    absolutePath = path.resolve(__dirname, `${themes[currentTheme].path}/static/${file}`);
                    currentTheme = themes[currentTheme].parent;
                }

                return (fs.existsSync(absolutePath)) ? absolutePath : null;
            });

            const filteredFiles = files.filter((file) => file !== null);
            if (filteredFiles.length > 0) {
                entries[entryKey] = {
                    import: filteredFiles,
                    layer: theme
                };
            }
        });
    });

    return entries;
};

const getOrderedScriptsEntries = (): { [key: string]: any } => {
    const entries: { [key: string]: any } = {};

    Object.keys(themes).forEach((theme) => {
        JS_VIEWS.forEach((view) => {
            const entryKey = `main-${theme}-${view}`;

            const js_files = new Map<string, number>();
            let currentTheme: string | null = theme;

            // Add files from the plugins
            let order = 0;
            const pluginKeys = Object.keys(plugins).sort();
            pluginKeys.forEach((plugin) => {
                plugins[plugin].get_scripts(view).forEach((file) => {
                    js_files.set(file, order);
                    order += 1;
                });
            });

            // Add files from the themes
            while (currentTheme) {
                themes[currentTheme].get_scripts(view).forEach((file) => {
                    if (!js_files.has(file)) {
                        js_files.set(file, order);
                        order += 1;
                    }
                });

                currentTheme = themes[currentTheme].parent;
            }

            const files = Array.from(js_files.keys()).map((file) => {
                let currentTheme: string | null = theme;

                let absolutePath = "";
                while (!fs.existsSync(absolutePath) && currentTheme) {
                    absolutePath = path.resolve(__dirname, `${themes[currentTheme].path}/static/${file}`);
                    currentTheme = themes[currentTheme].parent;
                }

                // If the file does not exist in the themes, search in the plugins
                if (!fs.existsSync(absolutePath)) {
                    for (const plugin of Object.values(plugins)) {
                        absolutePath = path.resolve(__dirname, `${plugin.path}/static/${file}`);
                        if (fs.existsSync(absolutePath)) {
                            break;
                        }
                    }
                }

                return (fs.existsSync(absolutePath)) ? absolutePath : null;
            });

            const filteredFiles = files.filter((file) => file !== null);
            // Sort files by the order specified in the map
            filteredFiles.sort((a, b) => {
                const fileA = a as string;
                const fileB = b as string;
                return js_files.get(fileA)! - js_files.get(fileB)!;
            });

            if (filteredFiles.length > 0) {
                entries[entryKey] = {
                    import: filteredFiles,
                    layer: theme
                };
            }
        });
    });

    return entries;
};

const getScriptAliases = (): { [key: string]: string } => {
    const aliases: { [key: string]: string } = {};

    Object.keys(plugins).forEach((plugin) => {
        const scriptsLocation = plugins[plugin].scripts_location;
        if (scriptsLocation) {
            aliases[plugin] = path.resolve(__dirname, `${plugins[plugin].path}/static/${scriptsLocation}`);
        }
    });

    return aliases;
};

const getThemeNames = (): string[] => {
    return Object.keys(themes);
}

export { createCSSEntries, resolveCSSIncludePaths, getOrderedScriptsEntries, getScriptAliases, getThemeNames };
