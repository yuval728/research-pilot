import * as React from 'react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Github, Mail } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/lib/hooks/use-auth';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

type AuthMode = 'signin' | 'signup' | 'magic';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [mode, setMode] = useState<AuthMode>('signin');
  const { signInWithProvider, signInWithEmail, signInWithPassword, signUpWithPassword } = useAuth();
  const navigate = useNavigate();

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === 'signup') {
      if (!email || !password || !confirmPassword) {
        toast.error('Please fill out all fields');
        return;
      }
      if (password !== confirmPassword) {
        toast.error('Passwords do not match');
        return;
      }
      try {
        const result = await signUpWithPassword(email, password);
        setPassword('');
        setConfirmPassword('');
        if (result.sessionCreated) {
          toast.success('Account created and signed in.');
          navigate('/library');
        } else {
          toast.success('Account created. Check your email to confirm your account.');
          setMode('signin');
        }
      } catch (err) {
        toast.error('Failed to create account');
      }
      return;
    }

    if (!email || !password) {
      toast.error('Please enter your email and password');
      return;
    }
    try {
      await signInWithPassword(email, password);
      toast.success('Signed in successfully');
      navigate('/library');
    } catch (err) {
      toast.error('Failed to sign in with password');
    }
  };

  const handleMagicLink = async () => {
    if (!email) {
      toast.error('Please enter your email');
      return;
    }
    try {
      await signInWithEmail(email);
      toast.success('Magic link sent to your email!');
    } catch (err) {
      toast.error('Failed to send magic link');
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#0a0a0a] p-4">
      <Card className="w-full max-w-md bg-[#0f0f0f] border-[#1a1a1a] shadow-2xl">
        <CardHeader className="space-y-2 text-center">
          <div className="flex justify-center mb-4">
            <div className="w-12 h-12 bg-primary rounded-lg flex items-center justify-center text-white text-2xl font-bold">
              RP
            </div>
          </div>
          <CardTitle className="text-2xl font-bold tracking-tight">Research Pilot</CardTitle>
          <CardDescription className="text-muted-foreground">
            Paper intelligence for ML engineers
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button variant="outline" className="w-full bg-transparent border-[#1a1a1a] hover:bg-secondary py-6" onClick={async () => {
            try {
              await signInWithProvider('github');
            } catch (e) {
              toast.error('GitHub sign-in failed');
            }
          }}>
            <Github className="mr-2 h-5 w-5" />
            Continue with GitHub
          </Button>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-[#1a1a1a]" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-[#0f0f0f] px-2 text-muted-foreground">or</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 rounded-lg border border-[#1a1a1a] p-1">
            {([
              ['signin', 'Sign In'],
              ['signup', 'Sign Up'],
              ['magic', 'Magic Link'],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={cn(
                  'rounded-md px-3 py-2 text-[10px] font-bold uppercase tracking-widest transition-colors',
                  mode === value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-secondary/60'
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <form onSubmit={handlePasswordLogin} className="space-y-4">
            <div className="space-y-2">
              <Input
                type="email"
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="bg-transparent border-[#1a1a1a] focus:ring-primary h-11"
              />
            </div>
            {mode !== 'magic' && (
              <div className="space-y-2">
                <Input
                  type="password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="bg-transparent border-[#1a1a1a] focus:ring-primary h-11"
                />
              </div>
            )}
            {mode === 'signup' && (
              <div className="space-y-2">
                <Input
                  type="password"
                  placeholder="Confirm password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="bg-transparent border-[#1a1a1a] focus:ring-primary h-11"
                />
              </div>
            )}
            {mode === 'signin' && (
              <Button type="submit" className="w-full bg-primary hover:bg-primary/90 py-6 font-semibold">
                Sign in with password
              </Button>
            )}
            {mode === 'signup' && (
              <Button type="submit" className="w-full bg-primary hover:bg-primary/90 py-6 font-semibold">
                Create account
              </Button>
            )}
            {mode === 'magic' && (
              <Button type="button" variant="outline" className="w-full bg-transparent border-[#1a1a1a] hover:bg-secondary py-6" onClick={handleMagicLink}>
                <Mail className="mr-2 h-5 w-5" />
                Send magic link
              </Button>
            )}
          </form>
        </CardContent>
        <CardFooter className="flex flex-col space-y-4">
          <p className="text-center text-xs text-muted-foreground px-8">
            By signing in you agree to our{' '}
            <a href="#" className="underline underline-offset-4 hover:text-primary">Terms of Service</a>{' '}
            and{' '}
            <a href="#" className="underline underline-offset-4 hover:text-primary">Privacy Policy</a>.
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}
