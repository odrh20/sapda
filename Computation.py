import copy
from SAPDA import SAPDA
from Configuration import *
import queue
from queue import PriorityQueue, Queue
from func_timeout import func_timeout, FunctionTimedOut, func_set_timeout
import random

"""
Class for SAPDA computations
"""

class Computation:

    def __init__(self, sapda, input_string, computation=None, configuration=None, transition_dict=None,
                 is_leaf=True):
        if computation is None:
            computation = []
        if transition_dict is None:
            transition_dict = dict()
        self.sapda = sapda
        self.input_string = input_string
        self.computation = computation
        self.configuration = configuration
        self.transition_dict = transition_dict
        self.is_leaf = is_leaf

        if configuration is None:
            # Initialise a single Leaf node
            self.configuration = Leaf(self.sapda, [self.sapda.initial_stack_symbol], self.sapda.initial_state,
                                      self.input_string)
            self.computation.append(self.configuration)

        self.update_transition_dict()


    def get_computation_list(self):
        comp_list = []
        for i in range(len(self.computation)):
            step = f"[u]Step {i+1}[/u]\n\n{self.computation[i].print_tree()}"
            comp_list.append(step)
        return comp_list

    def update(self, new_config):
        """
        Call this function at each step of the computation to update the configuration and append it to the computation.
        """

        self.computation.append(new_config)
        new_config_ = copy.deepcopy(new_config)
        self.configuration = new_config_
        self.update_transition_dict()
        if isinstance(self.configuration, Leaf):
            self.is_leaf = True
        else:
            self.is_leaf = False

    def synchronise_loop(self):
        """
        For a given configuration, call synchronise function until the configuration remains the same.
        """
        new_config = self.configuration.synchronise()
        if new_config != self.configuration:
            self.update(new_config)
            return self.synchronise_loop()
        return

    def is_accepting_config(self):
        """
        Accept if the configuration is a single leaf with no remaining input and empty stack.
        """
        return self.is_leaf and self.configuration.remaining_input == 'e' and self.configuration.has_empty_stack()

    def is_rejecting_config(self):
        """
        If there are any leaves that have no available transitions but have not emptied their stack, reject.
        If there are any leaves that have emptied their stack but still have remaining input, reject.
        """
        if self.is_accepting_config():
            return False

        if len(self.configuration.get_active_branches()) == 0:
            return True

        if self.configuration.get_tree_depth() > len(self.input_string):
            return True

        for leaf in self.transition_dict:
            if len(self.transition_dict[leaf]) == 0:
                return True

        for leaf in self.configuration.get_all_leaves():
            if not (leaf.has_valid_transition() or leaf.has_empty_stack()):
                return True

        return False

    def update_transition_dict(self):
        """
        Add every Leaf in current configuration to dictionary if it has a valid transition.
        Dictionary keys: SAPDA leaves (denoted as a quadruple of state, input, stack, internal stack)
        Dictionary values: List of available transitions, where each transition is a pair (letter to read, conjuncts)
        and conjuncts are pairs of (next state, string to push to stack).
        """
        for leaf in self.configuration.get_active_branches():
            if leaf.get_dict_key() not in self.transition_dict and leaf.has_valid_transition():

                # Check for transitions reading the next letter
                if leaf.remaining_input[0] in self.sapda.transitions[leaf.state][leaf.stack[0]]:
                    self.transition_dict[leaf.get_dict_key()] = []
                    for transition in self.sapda.transitions[leaf.state][leaf.stack[0]][
                        leaf.remaining_input[0]]:
                        self.transition_dict[leaf.get_dict_key()].append((leaf.remaining_input[0], transition))

                # Check for transitions reading 'e'
                if leaf.remaining_input[0] != 'e' and 'e' in self.sapda.transitions[leaf.state][leaf.stack[0]]:
                    if leaf.get_dict_key() not in self.transition_dict:
                        self.transition_dict[leaf.get_dict_key()] = []
                    for transition in self.sapda.transitions[leaf.state][leaf.stack[0]]['e']:
                        self.transition_dict[leaf.get_dict_key()].append(('e', transition))

    def order_active_branches(self):
        """
        Returns an ordered list of active leaves, where leaves with shortest remaining input are first.
        """
        active_branches = self.configuration.get_active_branches()
        branch_transitions = []
        for branch in active_branches:
            if branch.get_dict_key() not in self.transition_dict:
                print("found an active branch that is not in transition_dict. branch: ", branch.get_denotation())
            else:
                branch_transitions.append([branch, len(branch.remaining_input)+len(branch.stack)])

        branch_transitions.sort(key=lambda x: x[1])
        branches = []
        for branch, length in branch_transitions:
            branches.append(branch)
        return branches

    def is_deterministic_transition(self):
        """
        For the current configuration, check if any active branches have a deterministic transition.
        """
        for leaf in self.configuration.get_active_branches():
            if leaf.get_dict_key() in self.transition_dict and len(self.transition_dict[leaf.get_dict_key()]) == 1:
                return True
        return False

    def check_accept_reject(self):

        self.synchronise_loop()

        if self.is_accepting_config():
            return True, False
        if self.is_rejecting_config():
            return False, True
        return False, False

    def order_transitions(self, leaf):

        transitions = []
        for letter, conjuncts in self.transition_dict[leaf.get_dict_key()]:
            if letter != 'e' or len(conjuncts) == 1:
                transitions.append((letter, conjuncts))

        for letter, conjuncts in self.transition_dict[leaf.get_dict_key()]:
            if letter == 'e' and len(conjuncts) > 1:
                ordered_conjuncts = []
                for next_state, push_string in conjuncts:
                    if next_state != leaf.state or push_string[0] != leaf.stack[0]:
                        ordered_conjuncts.append((next_state, push_string))
                for next_state, push_string in conjuncts:
                    if next_state == leaf.state and push_string[0] == leaf.stack[0]:
                        ordered_conjuncts.append((next_state, push_string))
                conjunct_tuple = tuple(ordered_conjuncts)
                transitions.append((letter, conjunct_tuple))
        return transitions

    def run_deterministic_transitions(self):
        """
        From a given SAPDA configuration, runs transitions as long as there is only one available.
        Each transition is either an ordinary transition applied to a leaf, a conjunctive transition which splits a
        leaf into a tree, or collapsing of synchronised sibling leaves.
        After each transition, the new configuration is appended to the computation.
        Returns tuple of (Accept, Reject) booleans. If we reach a non-deterministic transition, both are False.
        """
        self.synchronise_loop()
        while self.is_deterministic_transition():

            # Check for synchronised leaves. If synchronisation occurs, call this function again.
            self.synchronise_loop()

            # Check if in an accepting configuration
            if self.is_accepting_config():
                return True, False

            # Check if in a rejecting configuration
            if self.is_rejecting_config():
                return False, True

            for leaf in self.configuration.get_active_branches():
                if leaf.get_dict_key() in self.transition_dict and len(self.transition_dict[leaf.get_dict_key()]) == 1:
                    letter, conjuncts = self.transition_dict[leaf.get_dict_key()][0]
                    new_config = self.configuration.find_leaf_for_transition(leaf, letter, conjuncts)
                    self.update(new_config)
                    self.synchronise_loop()

        # There is no deterministic transition available
        if self.is_accepting_config():
            return True, False
        if self.is_rejecting_config():
            return False, True
        return False, False

    def run_machine(self):
        """Run the machine on input string"""

        for letter in self.input_string:
            if self.input_string != 'e' and letter not in self.sapda.input_alphabet:
                return []

        accept, reject = self.run_deterministic_transitions()

        if accept:
            #print("Word accepted!\n")
            return self.get_computation_list()

        if reject:
            return []

        try:
            return self.dfs()
        except (RecursionError, FunctionTimedOut, RuntimeError, ValueError):
            return ['timeout']



    @func_set_timeout(20)
    def dfs(self, depth=0, path=None):

        if path is None:
            path = []

        # Iterate through each leaf in the configuration, starting with those with fewest available transitions.
        for leaf in self.order_active_branches():
            for index, (letter, conjuncts) in enumerate(self.order_transitions(leaf)):

                # Make a copy of the Computation object in case we need to backtrack later
                self_ = copy.deepcopy(self)

                # In the copy of the dictionary, remove all other transitions from this configuration
                self_.transition_dict[leaf.get_dict_key()] = [(letter, conjuncts)]
                accept, reject = self_.run_deterministic_transitions()

                if accept:
                    return self_.get_computation_list()

                if reject:
                    if index + 1 == len(self.order_transitions(leaf)):
                        if depth == 0:
                            return []
                        else:
                            # Need to backtrack
                            return self.backtrack(path, depth)


                if not (accept or reject):
                    path.append((leaf, letter, conjuncts, self.configuration, self.computation, self.transition_dict, self.is_leaf))
                    return self_.dfs(depth + 1, path)

    def backtrack(self, path, depth):
        if not path:
            return "Word rejected (tried to backtrack with empty path)"
        last_leaf, tried_letter, tried_conjuncts, last_config, last_computation, last_dict, last_is_leaf = path.pop()
        last_self = Computation(self.sapda, self.input_string, last_computation, last_config,
                                       last_dict, last_is_leaf)
        last_self.transition_dict[last_leaf.get_dict_key()].remove((tried_letter, tried_conjuncts))
        return last_self.dfs(depth - 1, path)


    @func_set_timeout(20)
    def bfs(self):

        # Create a Queue to keep track of all computation paths. Add current configuration to it.
        paths = Queue()
        paths.put(self)

        while not paths.empty():

            current_self = paths.get()
            for leaf in current_self.order_active_branches():

                for letter, conjuncts in current_self.order_transitions(leaf):
                    new_self = copy.deepcopy(current_self)
                    new_config = new_self.configuration.find_leaf_for_transition(leaf, letter, conjuncts)
                    new_self.update(new_config)
                    accept, reject = new_self.run_deterministic_transitions()
                    if accept:
                        return new_self.get_computation_list()
                    if reject:
                        continue
                    else:
                        paths.put(new_self)

        return []


sapda1 = SAPDA(
    name="Blocks of a's, b's and c's of equal length: {a[sup]n[/sup] b[sup]n[/sup] c[sup]n[/sup] | n > 0}",
    states={'q0', 'qbc+', 'qbc-', 'qac+', 'qac-', 'qb'},
    input_alphabet={'a', 'b', 'c'},
    stack_alphabet={'Z', 'A'},
    transitions={
        'q0': {'Z': {'e': {(('qbc+', 'Z'), ('qac+', 'Z'))}}
               },
        'qbc+': {'Z': {'a': {(('qbc+', 'Z'),)}, 'b': {(('qbc+', 'AZ'),)}},
                 'A': {'b': {(('qbc+', 'AA'),)}, 'c': {(('qbc-', 'e'),)}}
                 },
        'qbc-': {'A': {'c': {(('qbc-', 'e'),)}},
                 'Z': {'e': {(('q0', 'e'),)}}
                 },
        'qac+': {'Z': {'a': {(('qac+', 'AZ'),)}},
                 'A': {'a': {(('qac+', 'AA'),)}, 'b': {(('qb', 'A'),)}}
                 },
        'qb': {'A': {'b': {(('qb', 'A'),)}, 'c': {(('qac-', 'e'),)}},
               },
        'qac-': {'A': {'c': {(('qac-', 'e'),)}},
                 'Z': {'e': {(('q0', 'e'),)}}
                 },
    },
    initial_state='q0',
    initial_stack_symbol='Z'
)


# words with equal number of a's, b's and c's
sapda2 = SAPDA(
    name="Equal number of a's, b's and c's: {w ∈ Σ[sup]*[/sup] | |w|[sub]a[/sub] = |w|[sub]b[/sub] = |w|[sub]c[/sub]}",
    states={'q0', 'q1', 'q2'},
    input_alphabet={'a', 'b', 'c'},
    stack_alphabet={'Z', 'a', 'b', 'c'},
    transitions={
        'q0': {'Z': {'e': {(('q1', 'Z'), ('q2', 'Z'))}}
               },
        'q1': {'Z': {'a': {(('q1', 'aZ'),)}, 'b': {(('q1', 'bZ'),)}, 'c': {(('q1', 'Z'),)}, 'e': {(('q0', 'e'),)}},
               'a': {'a': {(('q1', 'aa'),)}, 'b': {(('q1', 'e'),)}, 'c': {(('q1', 'a'),)}},
               'b': {'a': {(('q1', 'e'),)}, 'b': {(('q1', 'bb'),)}, 'c': {(('q1', 'b'),)}},
               },
        'q2': {'Z': {'a': {(('q2', 'Z'),)}, 'b': {(('q2', 'bZ'),)}, 'c': {(('q2', 'cZ'),)}, 'e': {(('q0', 'e'),)}},
               'b': {'a': {(('q2', 'b'),)}, 'b': {(('q2', 'bb'),)}, 'c': {(('q2', 'e'),)}},
               'c': {'a': {(('q2', 'c'),)}, 'b': {(('q2', 'e'),)}, 'c': {(('q2', 'cc'),)}},
               },
    },
    initial_state='q0',
    initial_stack_symbol='Z'
)



# {w$uw : w,u ∈ {a,b}∗}
sapda3_ = SAPDA(
    states={'q0', 'qw', 'qe', 'qa1', 'qa2', 'qb1', 'qb2'},
    input_alphabet={'a', 'b', '$'},
    stack_alphabet={'Z', '#'},
    transitions={
        'q0': {'Z': {'a': {(('qa1', 'Z'), ('q0', 'Z'))}, 'b': {(('qb1', 'Z'), ('q0', 'Z'))}, '$': {(('qw', 'Z'),)}}
               },
        'qa1': {'Z': {'a': {(('qa1', '#Z'),)}, 'b': {(('qa1', '#Z'),)}, '$': {(('qa2', 'Z'),)}},
                '#': {'a': {(('qa1', '##'),)}, 'b': {(('qa1', '##'),)}, '$': {(('qa2', '#'),)}}
                },
        'qb1': {'Z': {'a': {(('qb1', '#Z'),)}, 'b': {(('qb1', '#Z'),)}, '$': {(('qb2', 'Z'),)}},
                '#': {'a': {(('qb1', '##'),)}, 'b': {(('qb1', '##'),)}, '$': {(('qb2', '#'),)}}
                },
        'qa2': {'Z': {'a': {(('qa2', 'Z'),), (('qe', 'Z'),)}, 'b': {(('qa2', 'Z'),)}},
                '#': {'a': {(('qa2', '#'),), (('qe', '#'),)}, 'b': {(('qa2', '#'),)}}
                },
        'qb2': {'Z': {'a': {(('qb2', 'Z'),)}, 'b': {(('qb2', 'Z'),), (('qe', 'Z'),)}},
                '#': {'a': {(('qb2', '#'),)}, 'b': {(('qb2', '#'),), (('qe', '#'),)}}
                },

        'qw': {'Z': {'a': {(('qw', 'Z'),), (('qe', 'e'),)}, 'b': {(('qw', 'Z'),), (('qe', 'e'),)}}
               },
        'qe': {'Z': {'e': {(('qe', 'e'),)}},
               '#': {'a': {(('qe', 'e'),)}, 'b': {(('qe', 'e'),)}}}
    },
    initial_state='q0',
    initial_stack_symbol='Z'
)

# {w$w : w∈ {a,b}∗} Reduplication with centre marker
sapda3 = SAPDA(
    name="Reduplication with centre marker: {w$w | w ∈ {a, b}[sup]*[/sup]}",
    states={'q0', 'ql', 'q', 'qw', 'qe', 'qa1', 'qa2', 'qb1', 'qb2'},
    input_alphabet={'a', 'b', '$'},
    stack_alphabet={'Z', '#'},
    transitions={
        'q0': {'Z': {'e': {(('ql', 'Z'), ('q', 'Z'))}}
               },
        'ql': {'Z': {'a': {(('ql', '#Z'),)}, 'b': {(('ql', '#Z'),)}, '$': {(('qe', 'Z'),)}},
               '#': {'a': {(('ql', '##'),)}, 'b': {(('ql', '##'),)}, '$': {(('qe', '#'),)}}
               },
        'q': {'Z': {'a': {(('qa1', 'Z'), ('q', 'Z'))}, 'b': {(('qb1', 'Z'), ('q', 'Z'))}, '$': {(('qw', 'Z'),)}}
               },
        'qa1': {'Z': {'a': {(('qa1', '#Z'),)}, 'b': {(('qa1', '#Z'),)}, '$': {(('qa2', 'Z'),)}},
                '#': {'a': {(('qa1', '##'),)}, 'b': {(('qa1', '##'),)}, '$': {(('qa2', '#'),)}}
                },
        'qb1': {'Z': {'a': {(('qb1', '#Z'),)}, 'b': {(('qb1', '#Z'),)}, '$': {(('qb2', 'Z'),)}},
                '#': {'a': {(('qb1', '##'),)}, 'b': {(('qb1', '##'),)}, '$': {(('qb2', '#'),)}}
                },
        'qa2': {'Z': {'a': {(('qa2', 'Z'),), (('qe', 'Z'),)}, 'b': {(('qa2', 'Z'),)}},
                '#': {'a': {(('qa2', '#'),), (('qe', '#'),)}, 'b': {(('qa2', '#'),)}}
                },
        'qb2': {'Z': {'a': {(('qb2', 'Z'),)}, 'b': {(('qb2', 'Z'),), (('qe', 'Z'),)}},
                '#': {'a': {(('qb2', '#'),)}, 'b': {(('qb2', '#'),), (('qe', '#'),)}}
                },

        'qw': {'Z': {'a': {(('qw', 'Z'),), (('qe', 'e'),)}, 'b': {(('qw', 'Z'),), (('qe', 'e'),)}}
               },
        'qe': {'Z': {'e': {(('qe', 'e'),)}},
               '#': {'a': {(('qe', 'e'),)}, 'b': {(('qe', 'e'),)}}}
    },
    initial_state='q0',
    initial_stack_symbol='Z'
)

# {0 ^(4^n) | n ≥ 0}
sapda4 = SAPDA(
    states={'q'},
    input_alphabet={'0'},
    stack_alphabet={'A', 'B', 'C', 'D', '0'},
    transitions={
        'q': {'A': {'e': {(('q', 'AC'), ('q', 'BB')), (('q', '0'),)}},
              'B': {'e': {(('q', 'AA'), ('q', 'BD')), (('q', '00'),)}},
              'C': {'e': {(('q', 'AB'), ('q', 'DD')), (('q', '000'),)}},
              'D': {'e': {(('q', 'AB'), ('q', 'CC'))}},
              '0': {'0': {(('q', 'e'),)}}
              }
    },
    initial_state='q',
    initial_stack_symbol='A'
)

sapda5 = SAPDA(
    states={'q'},
    input_alphabet={'a', 'b'},
    stack_alphabet={'S', 'a', 'b'},
    transitions={
        'q': {
              'S': {'e': {(('q', 'aaS'), ('q', 'aSa')), (('q', 'bbS'), ('q', 'bSb')), (('q', 'a'),), (('q', 'b'),)}},
              'a': {'a': {(('q', 'e'),)}},
              'b': {'b': {(('q', 'e'),)}},
              }
    },
    initial_state='q',
    initial_stack_symbol='S'
)

# a^n b^n (n>=0) (No conjunctive transitions, this is a PDA)
pda = SAPDA(
    states={'q0', 'q1', 'q2', 'q3'},
    input_alphabet={'a', 'b'},
    stack_alphabet={'Z', 'A'},
    transitions={
        'q0': {'Z': {'a': {(('q1', 'AZ'),)}, 'e': {(('q0', 'e'),)}}
               },
        'q1': {'A': {'a': {(('q1', 'AA'),)}, 'b': {(('q2', 'e'),)}},
               },
        'q2': {'A': {'b': {(('q2', 'e'),)}}, 'Z': {'e': {(('q3', 'e'),)}}
               }
    },
    initial_state='q0',
    initial_stack_symbol='Z'
)
