import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { AppRoutes } from './App';
import { UserContextProvider } from './context/UserContextProvider';
import './styles/tokens.css';
import './styles/global.css';

const root = document.getElementById('root');
if (!root) throw new Error('Root element #root not found.');

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <UserContextProvider>
        <AppRoutes />
      </UserContextProvider>
    </BrowserRouter>
  </StrictMode>,
);
