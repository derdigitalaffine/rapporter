import React from 'react';
import {addons} from 'storybook/preview-api';
import {STORY_FINISHED} from 'storybook/internal/core-events';
import '@fontsource-variable/nunito';
import i18n from '../src/brand-i18n';
import '../src/ux-i18n';
import '../src/additional-language-i18n';
import '../src/styles.css';
import '../src/sheets.css';
import '../src/smart.css';
import '../src/smart-extra.css';
import '../src/automation-guided.css';
import '../src/design-system.css';
import {applyAppearance} from '../src/appearance';
import '../src/appearance.css';
import '../src/form-primitives.css';
import '../src/feedback.css';
import '../src/accessibility.css';
import '../src/today-home.css';
import '../src/responsive.css';
import '../src/mobile-safety.css';
import '../src/app-navigation.css';
import '../src/layers.css';
import './workbench.css';

export default {
  parameters: {
    layout: 'fullscreen',
    a11y: {test: 'error'},
    viewport: {options: Object.fromEntries([[320,568], [390,844], [1024,768], [1440,900]].map(([width,height]) => [String(width), {
      name: `${width}px`, styles: {width: `${width}px`, height: `${height}px`}, type: width < 600 ? 'mobile' : 'desktop',
    }]))},
  },
  beforeEach: async () => {
    await i18n.changeLanguage('de');
    document.documentElement.lang = 'de';
    const channel = addons.getChannel();
    globalThis.__FAMILYOS_STORY_RESULT__ = null;
    const finished = result => {globalThis.__FAMILYOS_STORY_RESULT__ = result;};
    channel.on(STORY_FINISHED, finished);
    applyAppearance({profile: 'green', highContrast: false});
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (input, options) => {
      const url = new URL(typeof input === 'string' ? input : input.url, location.href);
      if (url.pathname === '/api/auth/session/') return Promise.resolve(Response.json({user: {id: 9001}}));
      if (url.pathname.startsWith('/api/')) return Promise.reject(new Error(`Unconfigured workbench fixture: ${url.pathname}`));
      return originalFetch(input, options);
    };
    return () => {globalThis.fetch = originalFetch; channel.off(STORY_FINISHED, finished);};
  },
  decorators: [(Story, context) => <main className="workbench-layout"><h1 className="form-sr-only">{context.name}</h1><Story/></main>],
};
