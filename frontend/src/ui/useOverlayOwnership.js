import {useInsertionEffect} from 'react';

// Release legacy inert attributes before Base UI's layout effects take ownership.
export default function useOverlayOwnership() {
  useInsertionEffect(() => {document.dispatchEvent(new Event('familyos:managed-overlay-mount'));}, []);
}
