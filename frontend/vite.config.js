import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

const root=fileURLToPath(new URL('.',import.meta.url));

export default defineConfig({
  plugins:[react()],
  build:{
    rollupOptions:{
      input:{
        app:resolve(root,'index.html'),
        superadmin:resolve(root,'superadmin/index.html'),
      },
    },
  },
});
