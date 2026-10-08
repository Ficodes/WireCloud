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
import { Configuration } from 'webpack';
import { resolveCSSIncludePaths, getThemeNames } from "./entries";
import MiniCssExtractPlugin = require('mini-css-extract-plugin');
import RemoveEmptyScriptsPlugin = require('webpack-remove-empty-scripts');
import * as esbuild from 'esbuild';

const generateCSSRules = (themeName: string): any => {
    return {
        issuerLayer: themeName,
        use: [
            MiniCssExtractPlugin.loader,
            {
                loader: 'css-loader',
                options: {
                    url: {
                        filter: (_: string, resourcePath: string): boolean => {
                            return !resourcePath.includes('src/wirecloud');
                        }
                    }
                }
            },
            {
                loader: 'sass-loader',
                options: {
                    sassOptions: (loaderContext: any) => {
                        // Check if it's sass
                        if (!loaderContext.resourcePath.endsWith('.scss')) {
                            return {};
                        }

                        return {
                            loadPaths: resolveCSSIncludePaths(themeName)
                        };
                    },
                    additionalData: (content: string, loaderContext: any): string => {
                        // Dynamically extract the context from the entry name
                        const isPlainCss = loaderContext.resourcePath.endsWith('.css');

                        if (isPlainCss) return content;

                        const contextMatch = loaderContext.resourcePath.match(/dist[\\/].*-([a-zA-Z0-9_-]+)$/);
                        const context = contextMatch?.[1] || 'platform';

                        return `$context: '${context}';\n${content}`;
                    }
                }
            }
        ]
    }
};

const cssRules = getThemeNames().map((pluginName) => generateCSSRules(pluginName));

const config: Configuration = {
    mode: process.env.NODE_ENV === 'production' ? 'production' : 'development',
    output: {
        path: path.resolve(__dirname, '../dist'),
        filename: (pathData) => {
            const chunkName = pathData.chunk?.name || '';
            const ext = path.extname(chunkName);
            if (ext === '.js') {
                return 'js/[name].js';
            } else if (ext === '.css') {
                return 'css/[name].css';
            } else {
                return 'js/[name].js';
            }
        },
        chunkFilename: 'js/[name].js'
    },
    experiments: {
        layers: true
    },
    resolve: {
        extensions: ['.js', '.ts', '.scss', '.css', '.ttf', '.woff', '.woff2', '.eot', '.otf'] // Resolve these file extensions
    },
    module: {
        rules: [
            {
                test: /\.css$/,
                include: /node_modules[\\/](monaco-editor|gridstack)/,
                use: [
                    'style-loader',
                    {
                        loader: 'css-loader',
                        options: {
                            url: false
                        }
                    }
                ]
            },
            {
                test: /\.(scss|css)$/,
                exclude: /node_modules/,
                oneOf: cssRules
            },
            {
                test: /\.[jt]sx?$/,
                exclude: /node_modules/,
                use: {
                    loader: 'esbuild-loader',
                    options: {
                        implementation: esbuild,
                        target: 'es2015'
                    }
                }
            },
            {
                test: /\.(ttf|woff|woff2|eot|otf)$/,
                type: 'asset/resource',
                generator: {
                    filename: 'fonts/[name][ext]'
                }
            }
        ]
    },
    performance: {
        maxEntrypointSize: 10240000, // 10 MiB
        maxAssetSize: 10240000, // 10 MiB
    },
    plugins: [
        new RemoveEmptyScriptsPlugin(),
        new MiniCssExtractPlugin({
            filename: 'css/[name].css',
        })
    ]
};

export default config;