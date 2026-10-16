export default {
  framework: '@storybook/react-vite',
  stories: ['../stories/**/*.stories.jsx'],
  addons: ['@storybook/addon-a11y', '@storybook/addon-vitest'],
  core: {disableTelemetry: true},
  staticDirs: [{from: '../public/brand', to: '/brand'}],
  viteFinal(config) {
    // The workbench has no application entry point, manifest or service worker.
    return {...config, publicDir: false};
  },
};
