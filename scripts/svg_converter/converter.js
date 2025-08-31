#!/usr/bin/env node

/**
 * High-performance SVG to PNG converter using sharp and svgo
 * Optimized for batch processing of cloud provider icons
 */

const sharp = require('sharp');
const { optimize } = require('svgo');
const glob = require('glob');
const pLimit = require('p-limit').default;
const fs = require('fs').promises;
const path = require('path');
const { performance } = require('perf_hooks');

class SvgConverter {
    constructor(options = {}) {
        this.concurrency = options.concurrency || 4;
        this.quality = options.quality || 'balanced';
        this.size = options.size || 256;
        this.verbose = options.verbose || false;
        this.limit = pLimit(this.concurrency);
        this.stats = {
            processed: 0,
            failed: 0,
            skipped: 0,
            totalTime: 0
        };

        // Quality presets
        this.qualityPresets = {
            fast: { pngQuality: 80, svgoMultipass: false },
            balanced: { pngQuality: 90, svgoMultipass: true },
            high: { pngQuality: 100, svgoMultipass: true }
        };
    }

    /**
     * Get quality settings based on preset
     */
    getQualitySettings() {
        return this.qualityPresets[this.quality] || this.qualityPresets.balanced;
    }

    /**
     * Optimize SVG using svgo
     */
    async optimizeSvg(svgPath) {
        try {
            const svgString = await fs.readFile(svgPath, 'utf8');
            const settings = this.getQualitySettings();

            const result = optimize(svgString, {
                path: svgPath,
                multipass: settings.svgoMultipass,
                plugins: [
                    {
                        name: 'preset-default',
                        params: {
                            overrides: {
                                // Keep viewBox for proper scaling
                                removeViewBox: false,
                                // Keep <title> and <desc> for accessibility
                                removeTitle: false,
                                removeDesc: false,
                                // Don't remove hidden elements (might be needed)
                                removeHiddenElems: false,
                                // Keep stroke and fill for proper rendering
                                removeUnknownsAndDefaults: false,
                            }
                        }
                    },
                    // Remove dimensions to allow scaling
                    'removeDimensions',
                    // Add explicit dimensions for consistent rendering
                    {
                        name: 'addAttributesToSVGElement',
                        params: {
                            attributes: [
                                { width: this.size },
                                { height: this.size }
                            ]
                        }
                    }
                ]
            });

            return result.data;
        } catch (error) {
            console.error(`Failed to optimize SVG ${svgPath}: ${error.message}`);
            // Return original SVG if optimization fails
            return await fs.readFile(svgPath, 'utf8');
        }
    }

    /**
     * Convert single SVG to PNG
     */
    async convertToPng(svgPath, pngPath) {
        const startTime = performance.now();

        try {
            // Ensure output directory exists
            const outputDir = path.dirname(pngPath);
            await fs.mkdir(outputDir, { recursive: true });

            // Optimize SVG
            const optimizedSvg = await this.optimizeSvg(svgPath);

            // Convert to PNG using sharp
            const settings = this.getQualitySettings();
            await sharp(Buffer.from(optimizedSvg))
                .resize(this.size, this.size, {
                    fit: 'contain',
                    background: { r: 0, g: 0, b: 0, alpha: 0 } // Transparent background
                })
                .png({
                    quality: settings.pngQuality,
                    compressionLevel: 9 // Max compression
                })
                .toFile(pngPath);

            const endTime = performance.now();
            const duration = (endTime - startTime) / 1000;

            this.stats.processed++;
            this.stats.totalTime += duration;

            if (this.verbose) {
                console.log(`✓ Converted ${path.basename(svgPath)} in ${duration.toFixed(3)}s`);
            }

            return { success: true, duration };
        } catch (error) {
            this.stats.failed++;
            console.error(`✗ Failed to convert ${svgPath}: ${error.message}`);
            return { success: false, error: error.message };
        }
    }

    /**
     * Convert a single file, replacing extension
     */
    async convertFile(svgPath, outputDir) {
        const basename = path.basename(svgPath, '.svg');
        const pngPath = path.join(outputDir, `${basename}.png`);

        // Check if PNG already exists and is newer than SVG
        try {
            const svgStat = await fs.stat(svgPath);
            const pngStat = await fs.stat(pngPath);

            if (pngStat.mtime > svgStat.mtime) {
                this.stats.skipped++;
                if (this.verbose) {
                    console.log(`⊙ Skipped ${path.basename(svgPath)} (up to date)`);
                }
                return { success: true, skipped: true };
            }
        } catch (error) {
            // PNG doesn't exist, proceed with conversion
        }

        return await this.convertToPng(svgPath, pngPath);
    }

    /**
     * Batch convert SVG files
     */
    async batchConvert(pattern, outputDir) {
        console.log(`Starting batch conversion with concurrency: ${this.concurrency}`);
        console.log(`Pattern: ${pattern}`);
        console.log(`Output: ${outputDir}`);

        const files = glob.sync(pattern);

        if (files.length === 0) {
            console.warn('No files found matching pattern');
            return this.stats;
        }

        console.log(`Found ${files.length} SVG files to process`);

        const startTime = performance.now();

        // Process files with concurrency limit
        const tasks = files.map(file =>
            this.limit(() => this.convertFile(file, outputDir))
        );

        // Report progress periodically
        const progressInterval = setInterval(() => {
            const progress = this.stats.processed + this.stats.failed + this.stats.skipped;
            const percent = (progress / files.length * 100).toFixed(1);
            process.stdout.write(`\rProgress: ${progress}/${files.length} (${percent}%)`);
        }, 100);

        await Promise.all(tasks);

        clearInterval(progressInterval);
        process.stdout.write('\r'); // Clear progress line

        const totalTime = (performance.now() - startTime) / 1000;

        // Print summary
        console.log('\n' + '='.repeat(50));
        console.log('Conversion Complete!');
        console.log('='.repeat(50));
        console.log(`Total files: ${files.length}`);
        console.log(`✓ Processed: ${this.stats.processed}`);
        console.log(`⊙ Skipped: ${this.stats.skipped}`);
        console.log(`✗ Failed: ${this.stats.failed}`);
        console.log(`Total time: ${totalTime.toFixed(2)}s`);

        if (this.stats.processed > 0) {
            const avgTime = this.stats.totalTime / this.stats.processed;
            console.log(`Average time per file: ${avgTime.toFixed(3)}s`);
        }

        return this.stats;
    }

    /**
     * Convert files in directory structure, preserving hierarchy
     */
    async convertDirectory(inputDir, outputDir) {
        console.log(`Converting directory: ${inputDir} -> ${outputDir}`);

        const pattern = path.join(inputDir, '**/*.svg');
        const files = glob.sync(pattern);

        if (files.length === 0) {
            console.warn('No SVG files found in directory');
            return this.stats;
        }

        console.log(`Found ${files.length} SVG files to process`);

        const startTime = performance.now();

        // Process files with preserved directory structure
        const tasks = files.map(file => {
            const relativePath = path.relative(inputDir, file);
            const outputPath = path.join(outputDir, relativePath).replace('.svg', '.png');

            return this.limit(() => this.convertToPng(file, outputPath));
        });

        // Report progress periodically
        const progressInterval = setInterval(() => {
            const progress = this.stats.processed + this.stats.failed;
            const percent = (progress / files.length * 100).toFixed(1);
            process.stdout.write(`\rProgress: ${progress}/${files.length} (${percent}%)`);
        }, 100);

        await Promise.all(tasks);

        clearInterval(progressInterval);
        process.stdout.write('\r'); // Clear progress line

        const totalTime = (performance.now() - startTime) / 1000;

        // Print summary
        console.log('\n' + '='.repeat(50));
        console.log('Directory Conversion Complete!');
        console.log('='.repeat(50));
        console.log(`Total files: ${files.length}`);
        console.log(`✓ Processed: ${this.stats.processed}`);
        console.log(`✗ Failed: ${this.stats.failed}`);
        console.log(`Total time: ${totalTime.toFixed(2)}s`);

        if (this.stats.processed > 0) {
            const avgTime = this.stats.totalTime / this.stats.processed;
            console.log(`Average time per file: ${avgTime.toFixed(3)}s`);
        }

        return this.stats;
    }
}

// CLI interface
if (require.main === module) {
    const yargs = require('yargs/yargs');
    const { hideBin } = require('yargs/helpers');

    const argv = yargs(hideBin(process.argv))
        .usage('Usage: $0 [options]')
        .option('pattern', {
            alias: 'p',
            type: 'string',
            description: 'Glob pattern for SVG files',
            demandOption: false
        })
        .option('input', {
            alias: 'i',
            type: 'string',
            description: 'Input directory (converts all SVG files recursively)',
            demandOption: false
        })
        .option('output', {
            alias: 'o',
            type: 'string',
            description: 'Output directory',
            demandOption: true
        })
        .option('concurrency', {
            alias: 'c',
            type: 'number',
            description: 'Number of parallel conversions',
            default: 4
        })
        .option('quality', {
            alias: 'q',
            type: 'string',
            description: 'Quality preset: fast, balanced, or high',
            default: 'balanced',
            choices: ['fast', 'balanced', 'high']
        })
        .option('size', {
            alias: 's',
            type: 'number',
            description: 'Output size in pixels',
            default: 256
        })
        .option('verbose', {
            alias: 'v',
            type: 'boolean',
            description: 'Verbose output',
            default: false
        })
        .check((argv) => {
            if (!argv.pattern && !argv.input) {
                throw new Error('Either --pattern or --input must be specified');
            }
            return true;
        })
        .help()
        .argv;

    const converter = new SvgConverter({
        concurrency: argv.concurrency,
        quality: argv.quality,
        size: argv.size,
        verbose: argv.verbose
    });

    // Run conversion
    (async () => {
        try {
            if (argv.input) {
                await converter.convertDirectory(argv.input, argv.output);
            } else {
                await converter.batchConvert(argv.pattern, argv.output);
            }

            process.exit(converter.stats.failed > 0 ? 1 : 0);
        } catch (error) {
            console.error('Fatal error:', error.message);
            process.exit(1);
        }
    })();
}

module.exports = SvgConverter;
